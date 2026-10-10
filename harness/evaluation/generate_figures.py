"""Benchmark figures (academic style) for the Probatio Labs harness.

Reads run logs (logs/run_*.json, including results/archive-*/logs/) and lab
aggregates (results/lab-*/results.json, including archives), then saves:

  1. time_turns_to_flag_by_lab  — grouped bars: mean time/turns to flag (+std)
  2. efficiency_distribution    — side-by-side violins: tokens and time by model
  3. judge_scores_heatmap       — mean mentor-rubric scores (rows) per model (cols)

All figures go to results/figures/ as PNG + PDF (300 DPI, tight bbox).

Usage:
    python3 -m harness.evaluation.generate_figures [--current-only]
"""

import glob
import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from harness.config import LOGS_DIR, RESULTS_DIR

FIGURES_DIR = os.path.join(RESULTS_DIR, "figures")
DPI = 300

# Display labels (pt-BR, for the TCC text). Identifiers stay in English.
LAB_LABELS = {1: "Lab 1", 2: "Lab 2", 3: "Lab 3"}
CRITERION_LABELS = {
    "correcao_tecnica": "Correção técnica",
    "eficiencia": "Eficiência",
    "seguranca_e_boas_praticas": "Segurança e boas práticas",
    "qualidade_didatica": "Qualidade didática",
}
CRITERION_ORDER = [
    "correcao_tecnica",
    "eficiencia",
    "seguranca_e_boas_praticas",
    "qualidade_didatica",
]
SCORE_COLUMNS = {
    "correcao_tecnica": "score_technical_accuracy",
    "eficiencia": "score_efficiency",
    "seguranca_e_boas_praticas": "score_safety",
    "qualidade_didatica": "score_didactics",
}

MODEL_SHORT_NAMES = {
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "nvidia/nemotron-3-ultra-550b-a55b:free": "Nemotron 3 Ultra",
    "apodex/apodex-1.1-mini:free": "Apodex 1.1 Mini",
    "qwen/qwen3.8-27b:free": "Qwen 3 27B",
}


def short_model_name(model_id):
    """Readable (short) model label for figures."""
    if model_id in MODEL_SHORT_NAMES:
        return MODEL_SHORT_NAMES[model_id]
    short = (model_id or "unknown").split("/")[-1].split(":")[0]
    return short.replace("-", " ").replace("_", " ").title()


def apply_academic_style():
    """Clean sans-serif style with a colorblind-friendly palette."""
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
    sns.set_theme(style="whitegrid", palette="colorblind")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"⚠️  skipping unreadable file: {path}: {e}")
        return None


def load_run_logs(results_dir=RESULTS_DIR, logs_dir=LOGS_DIR, include_archives=True):
    """Load run logs (current logs/ plus archived sessions, unless disabled)."""
    patterns = [os.path.join(logs_dir, "run_*.json")]
    if include_archives:
        patterns.append(os.path.join(results_dir, "archive-*", "logs", "run_*.json"))
    records = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            data = _read_json(path)
            if data is not None:
                records.append((path, data))
    return records


def load_result_aggregates(results_dir=RESULTS_DIR, include_archives=True):
    """Load per-lab results.json files (current plus archived sessions, unless disabled)."""
    patterns = [os.path.join(results_dir, "lab-*", "results.json")]
    if include_archives:
        patterns.append(os.path.join(results_dir, "archive-*", "lab-*", "results.json"))
    records = []
    for pattern in patterns:
        for path in sorted(glob.glob(pattern)):
            data = _read_json(path)
            if isinstance(data, list):
                records.append((path, data))
    return records


def _row_from_run_log(data):
    perf = data.get("performance") or {}
    eff = data.get("efficiency") or {}
    tokens = eff.get("tokens") or {}
    judge = data.get("llm_judge_evaluation") or {}
    scores = judge.get("scores") or {}
    failure = data.get("failure_analysis") or {}
    row = {
        "run_id": data.get("run_id"),
        "lab": data.get("scenario", "").split("—")[0].strip(),
        "model": data.get("model_evaluated"),
        "prompt_mode": data.get("prompt_mode", "full"),
        "success": bool(perf.get("flag_captured")),
        "state_verified": perf.get("state_verified"),
        "turn_count": eff.get("turn_count", 0),
        "execution_time_s": eff.get("execution_time_seconds", 0.0),
        "prompt_tokens": tokens.get("prompt_tokens", 0),
        "completion_tokens": tokens.get("completion_tokens", 0),
        "total_tokens": tokens.get("total_tokens", 0),
        "cost_usd": eff.get("estimated_cost_usd", 0.0),
        "judge_model": judge.get("model"),
        "judge_peso_ponderado": judge.get("peso_ponderado"),
        "judge_verdict": judge.get("veredicto"),
        "judge_error": judge.get("error"),
        "failure_category": failure.get("category") if failure.get("failed") else None,
    }
    for criterion, column in SCORE_COLUMNS.items():
        row[column] = scores.get(criterion)
    return row


def _lab_from_result(result, path):
    if result.get("lab") is not None:
        return result["lab"]
    import re

    match = re.search(r"lab-(\d+)", path)
    return int(match.group(1)) if match else 1


def _row_from_result_entry(result, path):
    return {
        "run_id": None,
        "lab": None,  # filled by caller
        "model": result.get("model"),
        "prompt_mode": result.get("prompt_mode", "full"),
        "success": bool(result.get("success")),
        "state_verified": None,
        "turn_count": result.get("turns", 0),
        "execution_time_s": result.get("wall_time_s", 0.0),
        "prompt_tokens": result.get("prompt_tokens", 0),
        "completion_tokens": result.get("completion_tokens", 0),
        "total_tokens": result.get("total_tokens", 0),
        "cost_usd": result.get("cost_usd", 0.0),
        "judge_model": None,
        "judge_peso_ponderado": None,
        "judge_verdict": None,
        "judge_error": None,
        "failure_category": None,
        **{column: None for column in SCORE_COLUMNS.values()},
    }


def _fingerprint(row):
    return (
        row.get("lab"),
        row.get("model"),
        row.get("prompt_mode"),
        row.get("total_tokens"),
        bool(row.get("success")),
    )


def build_runs_dataframe(results_dir=RESULTS_DIR, logs_dir=LOGS_DIR,
                         include_archives=True):
    """Consolidate run logs + lab aggregates into one DataFrame (no duplicates).

    Run logs win over aggregate rows via fingerprint dedupe.
    With include_archives=False, only the current session is loaded.
    """
    rows = []
    seen = set()

    for path, data in load_run_logs(results_dir, logs_dir, include_archives):
        lab_raw = _row_from_run_log(data)["lab"]
        row = _row_from_run_log(data)
        # scenario looks like "Lab 1 — ..." or "Desafio 01 — ...": recover the number
        import re

        scenario = data.get("scenario", "")
        match = re.search(r"(?:Lab|Desafio)\s*0?(\d)", scenario)
        row["lab"] = int(match.group(1)) if match else lab_raw
        row["source"] = path
        rows.append(row)
        seen.add(_fingerprint(row))

    for path, entries in load_result_aggregates(results_dir, include_archives):
        for result in entries:
            row = _row_from_result_entry(result, path)
            row["lab"] = _lab_from_result(result, path)
            row["source"] = path
            if _fingerprint(row) in seen:
                continue
            seen.add(_fingerprint(row))
            rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["lab_label"] = frame["lab"].map(LAB_LABELS).fillna(frame["lab"].astype(str))
    frame["model_short"] = frame["model"].map(short_model_name)
    if frame["prompt_mode"].nunique() > 1:
        frame["series"] = frame["model_short"] + " [" + frame["prompt_mode"] + "]"
    else:
        frame["series"] = frame["model_short"]
    return frame


def save_figure(fig, name):
    """Save PNG + PDF at 300 DPI with tight bbox. Returns the paths."""
    os.makedirs(FIGURES_DIR, exist_ok=True)
    paths = []
    for ext in ("png", "pdf"):
        path = os.path.join(FIGURES_DIR, f"{name}.{ext}")
        fig.savefig(path, dpi=DPI, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def plot_time_turns_to_flag(frame):
    """Graph 1: grouped bars of mean time/turns to flag per lab and model.

    Unlike success rate (saturated at 100%), time and turns actually separate
    labs and models — this is the difficulty-progression chart. Only
    successful runs count; error bars are one std across repetitions.
    """
    ok = frame[frame["success"]]
    if ok.empty:
        return _placeholder_figure(
            "Tempo e turnos até a flag por laboratório e modelo",
            "Sem runs bem-sucedidas nos dados atuais.",
            "time_turns_to_flag_by_lab",
        )

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sns.barplot(data=ok, x="lab_label", y="execution_time_s", hue="series",
                estimator="mean", errorbar="sd", ax=axes[0])
    axes[0].set_xlabel("Laboratório")
    axes[0].set_ylabel("Tempo médio até a flag (s)")
    axes[0].set_title("Tempo até a flag")
    axes[0].legend(title="Modelo", fontsize=8)

    sns.barplot(data=ok, x="lab_label", y="turn_count", hue="series",
                estimator="mean", errorbar="sd", ax=axes[1])
    axes[1].set_xlabel("Laboratório")
    axes[1].set_ylabel("Turnos médios até a flag")
    axes[1].set_title("Turnos até a flag")
    axes[1].set_ylim(bottom=0)  # error bars must not dip below zero
    axes[1].legend(title="Modelo", fontsize=8)

    fig.suptitle("Resolução: tempo e turnos até a flag (só sucessos, ±1 desvio)",
                 fontsize=12)
    fig.tight_layout()
    return save_figure(fig, "time_turns_to_flag_by_lab")


def plot_efficiency_violins(frame, min_observations=2):
    """Graph 2: side-by-side violins of tokens and execution time per model."""
    usable = frame.groupby("series").filter(lambda g: len(g) >= min_observations)
    dropped = sorted(set(frame["series"]) - set(usable["series"]))
    if dropped:
        print(f"ℹ️  violin plots: series with < {min_observations} runs skipped: {dropped}")

    fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharex=False)
    sns.violinplot(data=usable, x="series", y="total_tokens", inner="quart",
                   cut=0, ax=axes[0])
    axes[0].set_xlabel("Modelo")
    axes[0].set_ylabel("Total de tokens")
    axes[0].set_title("Distribuição de tokens por run")
    axes[0].tick_params(axis="x", rotation=15)

    sns.violinplot(data=usable, x="series", y="execution_time_s", inner="quart",
                   cut=0, ax=axes[1])
    axes[1].set_xlabel("Modelo")
    axes[1].set_ylabel("Tempo de execução (s)")
    axes[1].set_title("Distribuição de tempo por run")
    axes[1].tick_params(axis="x", rotation=15)

    fig.suptitle("Eficiência: dispersão e mediana das repetições", fontsize=12)
    fig.tight_layout()
    return save_figure(fig, "efficiency_distribution")


def _placeholder_figure(title, message, name):
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.axis("off")
    ax.set_title(title, fontsize=13)
    ax.text(0.5, 0.5, message, ha="center", va="center", fontsize=12,
            transform=ax.transAxes)
    fig.tight_layout()
    return save_figure(fig, name)


def plot_judge_scores_heatmap(frame):
    """Graph 3: heatmap of mean mentor-rubric scores (rows) per model (cols)."""
    judged = frame.dropna(subset=list(SCORE_COLUMNS.values()), how="all")
    if judged.empty:
        return _placeholder_figure(
            "Avaliação do juiz por dimensão e modelo",
            "Sem avaliações do juiz nos dados atuais.",
            "judge_scores_heatmap",
        )
    means = judged.groupby("series")[list(SCORE_COLUMNS.values())].mean().T
    # Rebuild row labels in rubric order, keeping only available columns.
    ordered = [c for c in CRITERION_ORDER if SCORE_COLUMNS[c] in means.index]
    means = means.loc[[SCORE_COLUMNS[c] for c in ordered]]
    means.index = [CRITERION_LABELS[c] for c in ordered]

    annot = means.map(lambda v: f"{v:.2f}" if pd.notna(v) else "n/a")
    fig, ax = plt.subplots(figsize=(max(8, 1.8 * len(means.columns) + 4), 5.5))
    sns.heatmap(means, annot=annot, fmt="", cmap="viridis", vmin=0, vmax=5,
                linewidths=0.5, ax=ax, mask=means.isna(),
                cbar_kws={"label": "Nota média (0–5)"})
    ax.set_xlabel("Modelo")
    ax.set_ylabel("Dimensão do juiz (mentor)")
    ax.set_title("Notas médias do juiz por dimensão e modelo")
    fig.tight_layout()
    return save_figure(fig, "judge_scores_heatmap")


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description="Generate benchmark figures")
    parser.add_argument("--current-only", action="store_true",
                        help="load only the current session (ignore results/archive-*)")
    args = parser.parse_args(argv)

    apply_academic_style()
    frame = build_runs_dataframe(include_archives=not args.current_only)
    print(f"📊 {len(frame)} runs carregadas "
          f"({frame['lab'].nunique() if len(frame) else 0} labs, "
          f"{frame['model'].nunique() if len(frame) else 0} modelos)")
    if frame.empty:
        print("Nenhum dado encontrado em logs/ ou results/.")
        return []
    paths = []
    paths += plot_time_turns_to_flag(frame)
    paths += plot_efficiency_violins(frame)
    paths += plot_judge_scores_heatmap(frame)
    print(f"🖼️  {len(paths)} figuras em {FIGURES_DIR}")
    for path in paths:
        print(f"   {path}")
    return paths


if __name__ == "__main__":
    main()
