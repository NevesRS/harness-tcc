"""LLM-as-judge: avalia o transcript na perspectiva do MENTOR.

Usa a rubrica mantida em harness/evaluation/judge.py (RUBRIC, escala 0–5 ponderada) via
build_judge_payload(), com qualquer backend de harness.llm.chat().
Modelo default: config.JUDGE_MODEL (gratuito); sobrescreva com --judge-model.
"""

import json
import re

from harness.config import JUDGE_MODEL
from harness.evaluation.judge import RUBRIC, build_judge_payload
from harness.llm import chat

CRITERIA = [c["criterio"] for c in RUBRIC]

JUDGE_OUTPUT_KEYS = ("notas", "peso_ponderado", "pontos_fortes",
                     "pontos_melhoria", "veredicto")


def parse_judge_json(text):
    """Extrai o JSON da resposta do juiz (tolera texto ao redor do bloco).

    Retorna o dict se contiver "notas", senão None.
    """
    if not text:
        return None
    candidates = re.findall(r"\{.*\}", text, re.DOTALL)
    for candidate in sorted(candidates, key=len, reverse=True):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and isinstance(data.get("notas"), dict):
            return data
    return None


def _validate(data):
    """Normaliza e valida o JSON do juiz. Retorna (ok, payload_ou_erro)."""
    notas = {
        key: data["notas"].get(key)
        for key in CRITERIA
    }
    for key, value in notas.items():
        if not isinstance(value, (int, float)) or not 0 <= value <= 5:
            return False, f"nota inválida para '{key}': {value!r} (esperado 0–5)"
    try:
        peso = float(data.get("peso_ponderado", 0))
    except (TypeError, ValueError):
        return False, f"peso_ponderado inválido: {data.get('peso_ponderado')!r}"
    veredicto = data.get("veredicto")
    if veredicto not in ("aprova", "reprova"):
        return False, f"veredicto inválido: {veredicto!r}"
    pontos_fortes = data.get("pontos_fortes") or []
    pontos_melhoria = data.get("pontos_melhoria") or []
    return True, {
        "scores": notas,
        "peso_ponderado": round(peso, 2),
        "pontos_fortes": list(pontos_fortes),
        "pontos_melhoria": list(pontos_melhoria),
        "veredicto": veredicto,
    }


def _error_result(model, message, usage=None, latency_s=0.0, raw=""):
    return {
        "model": model,
        "scores": None,
        "peso_ponderado": None,
        "pontos_fortes": [],
        "pontos_melhoria": [],
        "veredicto": None,
        "technical_scores": None,
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0},
        "latency_s": latency_s,
        "error": message,
        "raw": (raw or "")[:2000],
    }


def run_judge(transcript, model=None, lab_id=None, log=print):
    """Avalia um transcript com o modelo juiz. Retorna dict p/ o log da run.

    Nunca levanta exceção por conteúdo inesperado: resposta fora do formato
    vira {"error": ...} em vez de quebrar a sessão.
    """
    model = model or JUDGE_MODEL
    payload = build_judge_payload(transcript or {})
    messages = [
        {"role": "system", "content": payload["system"]},
        {"role": "user", "content": payload["user"]},
    ]
    log(f"  ⚖️  juiz ({model}) avaliando o transcript...")
    try:
        response = chat(messages, model)
    except Exception as e:
        return _error_result(model, f"falha na chamada do juiz: {e}")

    text = (response.get("message") or {}).get("content") or ""
    usage = response.get("usage") or {}
    latency = response.get("latency_s", 0.0)

    data = parse_judge_json(text)
    if data is None:
        return _error_result(model, "resposta do juiz fora do formato JSON esperado",
                             usage=usage, latency_s=latency, raw=text)

    ok, validated = _validate(data)
    if not ok:
        return _error_result(model, f"JSON do juiz inválido: {validated}",
                             usage=usage, latency_s=latency, raw=text)

    validated["model"] = model
    validated["technical_scores"] = None  # opcional (spec); não calculado por padrão
    validated["usage"] = usage
    validated["latency_s"] = latency
    validated["error"] = None
    if lab_id is not None:
        validated["lab"] = lab_id
    return validated
