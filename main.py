"""Entrypoint da harness: roda os modelos em série contra os labs do probatio-labs."""

import argparse
import os
import sys
import time

from harness.agent import PROMPT_MODES, run_agent
from harness.config import (
    API_KEY,
    JUDGE_MODEL,
    LABS,
    MAX_STEPS,
    MODELS,
    PAUSE_BETWEEN_MODELS,
    set_active_lab,
)
from harness.evaluation.llm_judge import run_judge
from harness.evaluation.metrics_collector import MetricsCollector
from harness.lab.runner import (
    archive_previous_results,
    ensure_lab,
    reset_for_run,
    save_run,
    stop_lab,
    write_summary,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Harness de avaliação de modelos no lab OT")
    parser.add_argument("--models", help="lista separada por vírgula (default: config.MODELS)")
    parser.add_argument("--lab", default=os.environ.get("HARNESS_LAB", "1"),
                        help='lab(s) a rodar, separados por vírgula: "1", "3" ou "1,2,3" '
                             "(default: env HARNESS_LAB ou 1)")
    parser.add_argument("--prompt", default=os.environ.get("HARNESS_PROMPT", "objective"),
                        choices=list(PROMPT_MODES),
                        help='"objective" (padrão do TCC: só objetivo, descobre como o aluno) '
                             'ou "full" (contexto completo, debug rápido)')
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS,
                        help="turnos máximos do agente por modelo")
    parser.add_argument("--runs", type=int, default=1,
                        help="repetições por modelo (default: 1)")
    parser.add_argument("--keep-lab", action="store_true",
                        help="não derruba os containers do lab ao final")
    parser.add_argument("--judge-model", default=None,
                        help=f"modelo do LLM-as-judge (default: {JUDGE_MODEL})")
    parser.add_argument("--no-judge", action="store_true",
                        help="pula a avaliação do juiz (só métricas determinísticas)")
    parser.add_argument("--report", action="store_true",
                        help="só gera o comparativo entre modelos (não roda nada)")
    return parser.parse_args()


def parse_labs(raw):
    try:
        labs = [int(x) for x in raw.split(",") if x.strip()]
    except ValueError:
        sys.exit(f'❌ --lab inválido: "{raw}" (use dígitos separados por vírgula, ex.: "1,2,3")')
    if not labs:
        sys.exit("❌ --lab vazio.")
    invalid = [lab for lab in labs if lab not in LABS]
    if invalid:
        sys.exit(f"❌ labs inválidos: {invalid} (esperado {sorted(LABS)})")
    return labs


def failed_result(model, error, lab, prompt_mode="full"):
    return {
        "model": model,
        "lab": lab,
        "prompt_mode": prompt_mode,
        "run": 0,
        "success": False,
        "flag": None,
        "wall_time_s": 0,
        "turns": 0,
        "commands": 0,
        "commands_failed": 0,
        "error_rate": 0.0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "error": str(error),
    }


def print_stats(lab, results):
    ok = [r for r in results if r["success"]]
    n = len(results)
    avg_time = sum(r["wall_time_s"] for r in ok) / len(ok) if ok else 0
    avg_turns = sum(r["turns"] for r in ok) / len(ok) if ok else 0
    avg_tokens = sum(r["total_tokens"] for r in results) / n
    err_rates = [r["error_rate"] for r in results if r["commands"]]
    avg_err = sum(err_rates) / len(err_rates) if err_rates else 0
    print(f"Lab {lab} — Sucesso: {len(ok)}/{n} | tempo médio (sucesso): {avg_time:.1f}s | "
          f"turnos médios: {avg_turns:.1f} | taxa de erro média: {avg_err:.1%} | "
          f"tokens médios: {avg_tokens:.0f}")


def main():
    args = parse_args()

    # Saída em tempo real mesmo quando redirecionada para pipe/arquivo
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if args.report:
        from harness.evaluation.report import generate_report
        generate_report()
        return

    if not API_KEY:
        sys.exit("❌ OPENROUTER_API_KEY não está definida (export ou .env).")

    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else MODELS
    labs = parse_labs(args.lab)
    judge_model = args.judge_model or JUDGE_MODEL

    archived = archive_previous_results()
    if archived:
        print(f"📦 Sessão anterior arquivada em {archived}")

    print("=== HARNESS — avaliação de modelos no laboratório OT ===")
    print(f"Labs: {', '.join(f'{n} — ' + LABS[n]['name'] for n in labs)}")
    print(f"Modelos: {', '.join(models)}")
    print(f"Rodadas por modelo: {args.runs}")
    print(f"Max steps: {args.max_steps}")
    print(f"Prompt: {args.prompt}")
    print(f"Juiz: {'desligado (--no-judge)' if args.no_judge else judge_model}\n")

    results_by_lab = {}
    md_paths = {}
    try:
        for lab_index, lab in enumerate(labs):
            set_active_lab(lab)
            print("==================================================")
            print(f"🧪 Lab {lab} — {LABS[lab]['name']}")
            print("==================================================")
            ensure_lab()
            lab_results = results_by_lab.setdefault(lab, [])

            for run in range(1, args.runs + 1):
                for model_index, model in enumerate(models):
                    print("--------------------------------------------------")
                    print(f"🤖 Modelo: {model} | rodada {run}/{args.runs}")
                    print("--------------------------------------------------")
                    reset_for_run()

                    try:
                        result, transcript = run_agent(model, max_steps=args.max_steps,
                                                       prompt_mode=args.prompt)
                        result["run"] = run
                        transcript_path = save_run(model, result, transcript, run, lab)
                    except Exception as e:  # continua com as demais rodadas
                        result = failed_result(model, e, lab, args.prompt)
                        transcript = {}
                        transcript_path = None
                        print(f"❌ Erro na rodada de {model}: {e}\n")

                    result["run"] = run
                    lab_results.append(result)
                    _, md_path = write_summary(lab_results, lab)
                    md_paths[lab] = md_path

                    status = "✅ flag obtida" if result["success"] else "❌ sem flag"
                    print(f"\n{status} | {result['wall_time_s']}s | {result['turns']} turnos | "
                          f"{result['commands']} comandos ({result['commands_failed']} c/ erro) | "
                          f"{result['total_tokens']} tokens")
                    if transcript_path:
                        print(f"📄 {transcript_path}\n")

                    # Métricas da run: juiz (mentor) + verificação determinística + log JSON
                    judge_result = None
                    if not args.no_judge and transcript:
                        try:
                            judge_result = run_judge(transcript, model=judge_model,
                                                     lab_id=lab)
                            if judge_result.get("error"):
                                print(f"  ⚠️  juiz: {judge_result['error']}")
                            else:
                                print(f"  ⚖️  juiz: {judge_result['veredicto']} "
                                      f"(ponderado {judge_result['peso_ponderado']})")
                        except Exception as e:  # juiz nunca quebra a sessão
                            print(f"  ⚠️  juiz falhou: {e}")
                            judge_result = None
                    collector = MetricsCollector(lab, model, run,
                                                     prompt_mode=args.prompt)
                    run_log = collector.finish(result, transcript, judge=judge_result,
                                               max_steps=args.max_steps)
                    log_path = collector.save(run_log)
                    verified = run_log["performance"]["state_verified"]
                    failure = run_log["failure_analysis"]
                    print(f"🧾 {log_path} | estado verificado: "
                          f"{'✅' if verified else '❌'}"
                          + (f" | falha: {failure['category']}" if failure["failed"] else ""))

                    last = (run == args.runs
                            and model_index == len(models) - 1
                            and lab_index == len(labs) - 1)
                    if not last:
                        print(f"⏸️  Pausa de {PAUSE_BETWEEN_MODELS}s...\n")
                        time.sleep(PAUSE_BETWEEN_MODELS)
    finally:
        for lab, lab_results in results_by_lab.items():
            _, md_path = write_summary(lab_results, lab)
            md_paths[lab] = md_path
        if not args.keep_lab:
            stop_lab()
            print("🛑 Lab derrubado (use --keep-lab para manter no ar).")

    print("\n=== RESUMO ===")
    for lab in sorted(results_by_lab):
        if lab in md_paths:
            with open(md_paths[lab], encoding="utf-8") as f:
                print(f.read())

    for lab in sorted(results_by_lab):
        print_stats(lab, results_by_lab[lab])

    for lab in sorted(md_paths):
        print(f"📊 {os.path.join(os.path.dirname(md_paths[lab]), 'results.json')}")
        print(f"📊 {md_paths[lab]}")


if __name__ == "__main__":
    main()
