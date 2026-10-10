"""Gera o comparativo entre modelos a partir de todos os transcripts."""

import glob
import json
import os
import re
from collections import defaultdict
from datetime import datetime

from harness.config import RESULTS_DIR


def load_transcripts():
    pattern = os.path.join(RESULTS_DIR, "**", "transcript.json")
    transcripts = []
    for path in sorted(glob.glob(pattern, recursive=True)):
        try:
            with open(path, encoding="utf-8") as f:
                transcript = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"⚠️  ignorando transcript ilegível: {path}: {e}")
            continue
        match = re.search(r"run-(\d+)", path)
        if match and "run" not in transcript["result"]:
            transcript["result"]["run"] = int(match.group(1))
        # Lab: campo do transcript > path (results/lab-N/...) > legado (= lab 1)
        if "lab" not in transcript:
            match_lab = re.search(r"lab-(\d+)", path)
            transcript["lab"] = (
                transcript["result"].get("lab")
                or (int(match_lab.group(1)) if match_lab else 1)
            )
        transcript["result"]["lab"] = transcript["lab"]
        # Prompt mode: transcripts antigos (experimento A) não têm o campo → full.
        if "prompt_mode" not in transcript["result"]:
            transcript["result"]["prompt_mode"] = transcript.get("prompt_mode", "full")
        transcripts.append(transcript)
    return transcripts


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def aggregate(transcripts):
    """Agrupa por (lab, modelo, prompt): runs, taxa de sucesso e médias."""
    by_key = defaultdict(list)
    for t in transcripts:
        r = t["result"]
        by_key[(r.get("lab", 1), r["model"], r.get("prompt_mode", "full"))].append(r)

    rows = []
    for (lab, model, prompt_mode), results in sorted(by_key.items()):
        ok = [r for r in results if r["success"]]
        err_rates = [r["error_rate"] for r in results if r["commands"]]
        rows.append({
            "lab": lab,
            "model": model,
            "prompt_mode": prompt_mode,
            "runs": len(results),
            "successes": len(ok),
            "success_rate": len(ok) / len(results) if results else 0.0,
            "avg_time_s": round(_mean([r["wall_time_s"] for r in ok]), 1),
            "avg_turns": round(_mean([r["turns"] for r in ok]), 1),
            "avg_commands": round(_mean([r["commands"] for r in results]), 1),
            "avg_error_rate": round(_mean(err_rates), 3),
            "avg_tokens": round(_mean([r["total_tokens"] for r in results])),
            "total_tokens": sum(r["total_tokens"] for r in results),
            "total_cost_usd": round(sum(r["cost_usd"] for r in results), 6),
        })
    return rows


def render_markdown(rows, transcripts):
    columns = [
        ("lab", "Lab"),
        ("model", "Modelo"),
        ("prompt_mode", "Prompt"),
        ("runs", "Runs"),
        ("success_rate", "Sucesso"),
        ("avg_time_s", "Tempo médio (s)"),
        ("avg_turns", "Turnos médios"),
        ("avg_commands", "Comandos médios"),
        ("avg_error_rate", "Taxa de erro média"),
        ("avg_tokens", "Tokens médios"),
        ("total_tokens", "Tokens total"),
        ("total_cost_usd", "Custo total (US$)"),
    ]
    lines = [
        "| " + " | ".join(label for _, label in columns) + " |",
        "|" + "|".join("---" for _ in columns) + "|",
    ]
    for r in rows:
        cells = []
        for key, _ in columns:
            value = r[key]
            if key == "success_rate":
                value = f"{value:.0%} ({r['successes']}/{r['runs']})"
            elif key == "avg_error_rate":
                value = f"{value:.1%}"
            cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")

    detail = [
        "",
        "## Detalhe por run",
        "",
        "| Lab | Modelo | Prompt | Run | Sucesso | Tempo (s) | Turnos | Comandos | Erros | Tokens |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in sorted(transcripts, key=lambda t: (t["result"].get("lab", 1),
                                                t["result"]["model"],
                                                t["result"].get("prompt_mode", "full"),
                                                t["result"].get("run", 0))):
        r = t["result"]
        detail.append(
            f"| {r.get('lab', 1)} | {r['model']} | {r.get('prompt_mode', 'full')} | "
            f"{r.get('run', '-')} | "
            f"{'✅' if r['success'] else '❌'} | "
            f"{r['wall_time_s']} | {r['turns']} | {r['commands']} | "
            f"{r['commands_failed']} | {r['total_tokens']} |"
        )

    return (
        "# Comparativo entre modelos\n\n"
        + "\n".join(lines)
        + "\n"
        + "\n".join(detail)
        + "\n"
    )


def generate_report():
    transcripts = load_transcripts()
    if not transcripts:
        print("Nenhum transcript encontrado em results/.")
        return None

    rows = aggregate(transcripts)
    md = render_markdown(rows, transcripts)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, "comparison.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)

    print(f"📊 {len(transcripts)} transcripts de {len(rows)} combinação(s) lab×modelo×prompt\n")
    print(md)
    print(f"Gerado em {datetime.now().isoformat(timespec='seconds')}")
    print(f"📊 {path}")
    return path
