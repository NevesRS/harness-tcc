"""Ciclo de vida do laboratório, persistência de transcript e métricas."""

import json
import os
import re
import shutil
from datetime import datetime

from harness.config import LOGS_DIR, RESULTS_DIR
from harness.lab.executor import lab_down, lab_up, reset_lab

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


def _model_dir(model, lab):
    safe = re.sub(r"[^\w.-]+", "__", model)
    path = os.path.join(RESULTS_DIR, f"lab-{lab}", safe)
    os.makedirs(path, exist_ok=True)
    return path


def save_run(model, result, transcript, run=1, lab=None):
    lab = lab if lab is not None else result.get("lab", 1)
    path = os.path.join(_model_dir(model, lab), f"run-{run:02d}", "transcript.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)
    return path


def write_summary(results, lab=1):
    lab_dir = os.path.join(RESULTS_DIR, f"lab-{lab}")
    os.makedirs(lab_dir, exist_ok=True)

    json_path = os.path.join(lab_dir, "results.json")
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

    md_path = os.path.join(lab_dir, "results.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Resultados da harness — Lab {lab}\n\n" + "\n".join(lines) + "\n")

    return json_path, md_path


def stop_lab():
    return lab_down()


def archive_previous_results():
    """Move resultados + logs da sessão anterior para results/archive-<ts>/.

    Evita que write_summary/transcripts/logs de uma nova sessão sobrescrevam
    os     dados da anterior (os logs usam run_id repetido por sessão). Archives
    antigos (archive-*) ficam como irmãos no mesmo nível — nunca aninhados.
    Retorna o destino (ou None se não havia nada).
    """
    moves = []  # (origem, destino)
    if os.path.isdir(RESULTS_DIR):
        moves += [
            (os.path.join(RESULTS_DIR, e), e)
            for e in os.listdir(RESULTS_DIR)
            if not e.startswith("archive-")
        ]
    log_entries = []
    if os.path.isdir(LOGS_DIR):
        log_entries = os.listdir(LOGS_DIR)
    if not moves and not log_entries:
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(RESULTS_DIR, f"archive-{ts}")
    os.makedirs(dest)
    for src, name in moves:
        shutil.move(src, os.path.join(dest, name))
    if log_entries:
        logs_dest = os.path.join(dest, "logs")
        os.makedirs(logs_dest)
        for entry in log_entries:
            shutil.move(os.path.join(LOGS_DIR, entry),
                        os.path.join(logs_dest, entry))
    return dest
