"""Cliente Google AI (Gemini) com interface compatível com llm.chat().

Permite rodar a harness com modelos do Google AI Studio trocando só o nome
do modelo (ex.: --models "gemini-3.1-flash-lite").

Usa a API Chat (client.chats.create + send_message) conforme a recomendação
do SDK em vez de Models.generate_content direto.
"""

import os
import random
import re
import time

from google import genai
from google.genai import types

from harness.config import MAX_RETRIES

RETRYABLE_CODES = {429, 500, 502, 503, 504}


def _api_key():
    key = (os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        raise SystemExit(
            "❌ GOOGLE_API_KEY (ou GEMINI_API_KEY) não está definida.\n"
            "   Adicione ao .env ou exporte a variável."
        )
    return key


def _convert_messages(messages):
    """Converte messages (system/user/assistant) p/ contents + system_instruction do Gemini."""
    system_parts = []
    contents = []
    for message in messages:
        role = message.get("role")
        text = message.get("content") or ""
        if role == "system":
            system_parts.append(text)
        elif role == "assistant":
            contents.append(types.Content(role="model", parts=[types.Part(text=text)]))
        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
    return contents, "\n".join(system_parts) or None


def _status_code(exc):
    """Extrai o status HTTP de erros da SDK (ou None se desconhecido)."""
    for attr in ("code", "status"):
        value = getattr(exc, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                value = None
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    match = re.search(r"\b(4\d\d|5\d\d)\b", str(exc))
    return int(match.group(1)) if match else None


def _split_last_user(contents):
    """Separa o histórico da última mensagem do usuário (a que será enviada)."""
    if contents and contents[-1].role == "user":
        text = "".join((part.text or "") for part in contents[-1].parts)
        return contents[:-1], text
    return contents, ""


def chat(messages, model, reasoning=True):
    """Chama o Gemini via API Chat (recomendada pelo SDK) com retry em 429/5xx.

    Mesmo contrato de llm.chat(): {"message": dict, "usage": dict, "latency_s": float}.
    O parâmetro `reasoning` é ignorado — thinking é intrínseco ao Gemini.
    """
    client = genai.Client(api_key=_api_key())
    contents, system_instruction = _convert_messages(messages)
    history, next_message = _split_last_user(contents)

    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        # Não usamos tools: desliga o AFC explicitamente (é o que o próprio
        # Chat.send_message faz internamente) e evita o warning do SDK.
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for attempt in range(MAX_RETRIES):
        start = time.monotonic()
        try:
            session = client.chats.create(model=model, config=config, history=history)
            response = session.send_message(next_message)
        except Exception as e:
            status = _status_code(e)
            if status is not None and status not in RETRYABLE_CODES:
                raise  # erro permanente (400, 403, 404...) → propaga
            if attempt == MAX_RETRIES - 1:
                raise RuntimeError(
                    f"Falha após {MAX_RETRIES} tentativas em {model}: {e}"
                ) from e
            wait = min(5 * (2 ** attempt), 45) + random.uniform(0, 3)
            print(
                f"⏳ {e.__class__.__name__}(status={status}) em {model}, "
                f"retry {attempt + 1}/{MAX_RETRIES - 1} em {wait:.0f}s..."
            )
            time.sleep(wait)
            continue

        latency = time.monotonic() - start
        usage = getattr(response, "usage_metadata", None)
        prompt_tokens = (getattr(usage, "prompt_token_count", 0) or 0)
        candidate_tokens = (getattr(usage, "candidates_token_count", 0) or 0)
        thought_tokens = (getattr(usage, "thoughts_token_count", 0) or 0)
        try:
            text = response.text or ""
        except Exception:
            text = ""

        return {
            "message": {"content": text},
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": candidate_tokens + thought_tokens,
                "cost": 0.0,  # Google não expõe custo na response; preencher manualmente se quiser
            },
            "latency_s": round(latency, 2),
        }

    raise RuntimeError(f"Falha em {model}: loop de retry encerrado inesperadamente")
