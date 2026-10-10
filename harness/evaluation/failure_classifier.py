"""Taxonomia de falhas (Failure Analysis): classifica por regras o motivo da falha.

Categorias (conforme docs/especificacao_de_metricas):
  GIVE_UP, TIMEOUT_OR_ROUNDS_EXCEEDED, TOOL_MISUSE, DOMAIN_KNOWLEDGE_GAP,
  HALLUCINATION_LOOP
"""

import re
from collections import Counter

from harness.config import MAX_STEPS

# Frases que indicam desistência explícita (última mensagem do assistente).
GIVE_UP_PATTERNS = [
    r"\bdesisto\b",
    r"não consigo",
    r"nao consigo",
    r"\bimpossível\b",
    r"\bimpossivel\b",
    r"não há como",
    r"sem solução",
    r"\bi give up\b",
    r"\bi cannot\b.*\b(proceed|succeed|continue)\b",
    r"\bunable to\b.*\b(proceed|succeed)\b",
    r"\bgiving up\b",
]

REPEAT_THRESHOLD = 3  # mesmo comando executado N+ vezes → HALLUCINATION_LOOP
ERROR_RATE_THRESHOLD = 0.5  # com >= 3 comandos → TOOL_MISUSE


def _normalize_command(command):
    return re.sub(r"\s+", " ", (command or "").strip())


def _assistant_texts(transcript):
    return [
        step.get("assistant") or ""
        for step in transcript.get("steps", [])
        if step.get("assistant")
    ]


def _executed_commands(transcript):
    commands = []
    for step in transcript.get("steps", []):
        for cmd in step.get("commands", []):
            norm = _normalize_command(cmd.get("command"))
            if norm:
                commands.append(norm)
    return commands


def classify_failure(result, transcript, max_steps=MAX_STEPS):
    """Classifica a falha de uma run. Retorna {"failed", "category", "details"}.

    Em caso de sucesso: {"failed": False, "category": None, "details": None}.
    Precedência: GIVE_UP > TIMEOUT > HALLUCINATION_LOOP > TOOL_MISUSE > GAP.
    """
    transcript = transcript or {}
    if result.get("success"):
        return {"failed": False, "category": None, "details": None}

    turns = result.get("turns", 0)
    commands = _executed_commands(transcript)
    error_rate = result.get("error_rate", 0.0) or 0.0
    exec_error = result.get("error")

    def with_exec_error(details):
        # Erro de infraestrutura (ex.: 429 esgotado) não é falha do agente:
        # registra na evidência para não confundir a leitura da categoria.
        if exec_error:
            return f"{details} | erro de execução: {str(exec_error)[:160]}"
        return details

    # 1. Desistência explícita (última mensagem do assistente).
    texts = _assistant_texts(transcript)
    if texts:
        last = texts[-1].lower()
        if any(re.search(p, last) for p in GIVE_UP_PATTERNS):
            return {
                "failed": True,
                "category": "GIVE_UP",
                "details": with_exec_error(f"desistência declarada no turno {turns}"),
            }

    # 2. Esgotou o orçamento de turnos.
    if turns >= max_steps:
        return {
            "failed": True,
            "category": "TIMEOUT_OR_ROUNDS_EXCEEDED",
            "details": with_exec_error(f"{turns}/{max_steps} turnos usados sem obter a flag"),
        }

    # 3. Repetiu o mesmo comando sem variar.
    if commands:
        top, count = Counter(commands).most_common(1)[0]
        if count >= REPEAT_THRESHOLD:
            return {
                "failed": True,
                "category": "HALLUCINATION_LOOP",
                "details": with_exec_error(f"mesmo comando repetido {count}x: {top[:160]}"),
            }

    # 4. Erro persistente de sintaxe/uso das ferramentas.
    if len(commands) >= 3 and error_rate >= ERROR_RATE_THRESHOLD:
        failed = result.get("commands_failed", 0)
        return {
            "failed": True,
            "category": "TOOL_MISUSE",
            "details": with_exec_error(f"{failed}/{len(commands)} comandos com erro "
                                          f"(taxa {error_rate:.0%})"),
        }

    # 5. Falhou sem encaixar nas anteriores → lacuna de domínio.
    return {
        "failed": True,
        "category": "DOMAIN_KNOWLEDGE_GAP",
        "details": with_exec_error(f"sem flag em {turns} turno(s)/{len(commands)} comando(s), "
                                          "sem padrão dominante de erro"),
    }
