"""Backends de LLM da harness.

chat() despacha pelo nome do modelo:
  - gemini*  → Google AI (harness.llm.google)
  - demais   → OpenRouter (harness.llm.openrouter)

Os imports são lazy: a SDK do Google só é carregada quando um modelo gemini*
é usado.
"""


def chat(messages, model, reasoning=True):
    if model.startswith("gemini"):
        from harness.llm import google
        return google.chat(messages, model, reasoning=reasoning)
    from harness.llm import openrouter
    return openrouter.chat(messages, model, reasoning=reasoning)
