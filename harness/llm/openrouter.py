"""Cliente OpenRouter com retry/backoff e coleta de usage (tokens/custo)."""

import json
import random
import time

import requests

from harness.config import API_KEY, API_URL, MAX_RETRIES, REQUEST_TIMEOUT, RETRY_STATUS

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


def _wait_before(attempt, response):
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    return min(5 * (2 ** attempt), 45) + random.uniform(0, 3)


def chat(messages, model, reasoning=True):
    """POST único com retry em 429/5xx e em respostas malformadas (sem choices).

    Retorna dict: {"message": dict, "usage": dict, "latency_s": float}.
    """
    payload = {
        "model": model,
        "messages": messages,
        "usage": {"include": True},
    }
    if reasoning:
        payload["reasoning"] = {"enabled": True}

    last_error = "sem tentativa"
    for attempt in range(MAX_RETRIES):
        start = time.monotonic()
        response = requests.post(
            API_URL,
            headers=HEADERS,
            data=json.dumps(payload),
            timeout=REQUEST_TIMEOUT,
        )
        latency = time.monotonic() - start

        if response.status_code in RETRY_STATUS:
            last_error = f"HTTP {response.status_code}"
        else:
            try:
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.HTTPError:
                raise  # erro não-retryável (401, 400...) → propaga para o chamador
            except ValueError as e:
                last_error = f"corpo inválido: {e}"
            else:
                choices = data.get("choices") or []
                message = choices[0].get("message") if choices else None
                if message is None:
                    last_error = "resposta sem choices/message: " + json.dumps(data)[:300]
                else:
                    usage = data.get("usage") or {}
                    return {
                        "message": message,
                        "usage": {
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "cost": usage.get("cost", 0.0),
                        },
                        "latency_s": round(latency, 2),
                    }

        # daqui em diante: erro retryável (429/5xx, corpo inválido ou sem choices)
        if attempt == MAX_RETRIES - 1:
            break
        wait = _wait_before(attempt, response)
        print(
            f"⏳ {last_error} em {model}, "
            f"retry {attempt + 1}/{MAX_RETRIES - 1} em {wait:.0f}s..."
        )
        time.sleep(wait)

    raise RuntimeError(f"Falha após {MAX_RETRIES} tentativas em {model}: {last_error}")
