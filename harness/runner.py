"""Ciclo de vida do laboratório, persistência de transcript e métricas."""

import json
import os
import re
import shutil
from datetime import datetime

from harness.config import RESULTS_DIR
from harness.executor import lab_down, lab_up, reset_lab

SUMMARY_COLUMNS = [
    ("run", "Run"),
    ("model", "Modelo"),
    ("success", "Sucesso"),
    ("wall_time_s", "Tempo (s)"),
    ("turns", "Turnos"),
    ("commands", "Comandos"),
    ("commands_failed", "Comandos c/ erro"),
    ("error_rate", "Taxa de erro"),
    ("total_tokens", "Tokens"),
    ("cost_usd", "Custo (US$)"),
]


def ensure_lab():
    ok, msg = lab_up()
    if not ok:
        raise RuntimeError(f"Falha ao subir o lab: {msg}")
    print(f"  🧪 Lab: {msg}")


def reset_for_run():
    ok, msg = reset_lab()
    if not ok:
        raise RuntimeError(f"Falha ao resetar o lab: {msg}")
    print(f"  🔄 {msg}")


def _model_dir(model):
    safe = re.sub(r"[^\w.-]+", "__", model)
    path = os.path.join(RESULTS_DIR, safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_run(model, result, transcript, run=1):
    path = os.path.join(_model_dir(model), f"run-{run:02d}", "transcript.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    return path


def write_summary(results):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    json_path = os.path.join(RESULTS_DIR, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    lines = [
        "| " + " | ".join(label for _, label in SUMMARY_COLUMNS) + " |",
        "|" + "|".join("---" for _ in SUMMARY_COLUMNS) + "|",
    ]
    for r in results:
        row = []
        for key, _ in SUMMARY_COLUMNS:
            value = r.get(key)
            if key == "success":
                value = "✅" if value else "❌"
            elif key == "error_rate":
                value = f"{value:.1%}"
            row.append(str(value))
        lines.append("| " + " | ".join(row) + " |")

    md_path = os.path.join(RESULTS_DIR, "results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Resultados da harness\n\n" + "\n".join(lines) + "\n")

    return json_path, md_path


def stop_lab():
    return lab_down()


def archive_previous_results():
    """Move os resultados da sessão anterior para results/archive-<ts>/.

    Evita que write_summary/transcripts de uma nova sessão sobrescrevam os
    dados da anterior. Retorna o destino (ou None se não havia nada).
    """
    if not os.path.isdir(RESULTS_DIR):
        return None
    entries = os.listdir(RESULTS_DIR)
    if not entries:
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(RESULTS_DIR, f"archive-{ts}")
    os.makedirs(dest)
    for entry in entries:
        shutil.move(os.path.join(RESULTS_DIR, entry), os.path.join(dest, entry))
    return dest
