"""Entrypoint da harness: roda os modelos em série contra o laboratório OT."""

import argparse
import sys
import time

from harness.agent import run_agent
from harness.config import API_KEY, MAX_STEPS, MODELS, PAUSE_BETWEEN_MODELS
from harness.runner import (
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
    parser.add_argument("--max-steps", type=int, default=MAX_STEPS,
                        help="turnos máximos do agente por modelo")
    parser.add_argument("--runs", type=int, default=1,
                        help="repetições por modelo (default: 1)")
    parser.add_argument("--keep-lab", action="store_true",
                        help="não derruba os containers do lab ao final")
    parser.add_argument("--report", action="store_true",
                        help="só gera o comparativo entre modelos (não roda nada)")
    return parser.parse_args()


def failed_result(model, error):
    return {
        "model": model,
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


def main():
    args = parse_args()

    # Saída em tempo real mesmo quando redirecionada para pipe/arquivo
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except AttributeError:
        pass

    if args.report:
        from harness.report import generate_report
        generate_report()
        return

    if not API_KEY:
        sys.exit("❌ OPENROUTER_API_KEY não está definida (export ou .env).")

    models = [m.strip() for m in args.models.split(",") if m.strip()] if args.models else MODELS

    archived = archive_previous_results()
    if archived:
        print(f"📦 Sessão anterior arquivada em {archived}")

    print("=== HARNESS — avaliação de modelos no laboratório OT ===")
    print(f"Modelos: {', '.join(models)}")
    print(f"Rodadas por modelo: {args.runs}")
    print(f"Max steps: {args.max_steps}\n")

    results = []
    ensure_lab()

    try:
        for run in range(1, args.runs + 1):
            for index, model in enumerate(models):
                print("--------------------------------------------------")
                print(f"🤖 Modelo: {model} | rodada {run}/{args.runs}")
                print("--------------------------------------------------")
                reset_for_run()

                try:
                    result, transcript = run_agent(model, max_steps=args.max_steps)
                    result["run"] = run
                    transcript_path = save_run(model, result, transcript, run)
                except Exception as e:  # continua com as demais rodadas
                    result = failed_result(model, e)
                    transcript_path = None
                    print(f"❌ Erro na rodada de {model}: {e}\n")

                result["run"] = run
                results.append(result)
                write_summary(results)

                status = "✅ flag obtida" if result["success"] else "❌ sem flag"
                print(f"\n{status} | {result['wall_time_s']}s | {result['turns']} turnos | "
                      f"{result['commands']} comandos ({result['commands_failed']} c/ erro) | "
                      f"{result['total_tokens']} tokens")
                if transcript_path:
                    print(f"📄 {transcript_path}\n")

                last = run == args.runs and index == len(models) - 1
                if not last:
                    print(f"⏸️  Pausa de {PAUSE_BETWEEN_MODELS}s...\n")
                    time.sleep(PAUSE_BETWEEN_MODELS)
    finally:
        json_path, md_path = write_summary(results)
        if not args.keep_lab:
            stop_lab()
            print("🛑 Lab derrubado (use --keep-lab para manter no ar).")

    print("\n=== RESUMO ===")
    with open(md_path, encoding="utf-8") as f:
        print(f.read())

    if results:
        ok = [r for r in results if r["success"]]
        n = len(results)
        avg_time = sum(r["wall_time_s"] for r in ok) / len(ok) if ok else 0
        avg_turns = sum(r["turns"] for r in ok) / len(ok) if ok else 0
        avg_tokens = sum(r["total_tokens"] for r in results) / n
        err_rates = [r["error_rate"] for r in results if r["commands"]]
        avg_err = sum(err_rates) / len(err_rates) if err_rates else 0
        print(f"Sucesso: {len(ok)}/{n} | tempo médio (sucesso): {avg_time:.1f}s | "
              f"turnos médios: {avg_turns:.1f} | taxa de erro média: {avg_err:.1%} | "
              f"tokens médios: {avg_tokens:.0f}")

    print(f"📊 {json_path}")
    print(f"📊 {md_path}")


if __name__ == "__main__":
    main()
