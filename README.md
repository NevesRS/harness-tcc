# Harness de Avaliação de Modelos — Laboratório OT

Harness que avalia LLMs como **agentes/mentores** de um laboratório de segurança
ICS/OT ([probatio-labs](../probatio-labs)): o modelo recebe o desafio, propõe
comandos, a harness executa no container `attacker` e devolve as saídas até ele
obter a flag (ou estourar o limite de turnos).

---

## Requisitos

- Docker Engine + Docker Compose (lab `probatio-labs`)
- Python 3.11+
- Dependências:

```bash
pip install --break-system-packages -r requirements.txt
```

- `.env` na raiz com as chaves:

```bash
OPENROUTER_API_KEY=sk-or-...
GOOGLE_API_KEY=...
```

> O `.env` é carregado automaticamente por `harness/env_loader.py` (sem dependências externas).

---

## Como rodar

### 1. Subir o laboratório

```bash
cd ../probatio-labs
docker compose up -d attacker target
```

A harness também sobe o lab sozinha (`ensure_lab`) e faz **restart do target +
limpeza da flag antiga antes de cada rodada** (flag nova por run, sem falso positivo).

### 2. Rodar a avaliação

```bash
# Padrão: modelos de harness.config.MODELS, 1 run cada
python3 -u main.py

# 5 runs de um modelo (recomendado para estatística)
python3 -u main.py --models "gemini-3.1-flash-lite" --runs 5 --keep-lab

# Modelos do OpenRouter (mesmo formato do gateway)
python3 -u main.py --models "nvidia/nemotron-3-ultra-550b-a55b:free,qwen/qwen3.8-27b:free" --runs 5

# Só gerar o comparativo (não executa nada)
python3 -u main.py --report
```

**Seleção de backend automática:** modelo começa com `gemini` → Google AI
(`harness/llm/google.py`); demais → OpenRouter (`harness/llm/openrouter.py`).

> Use sempre `-u` (o entrypoint também ativa line-buffering) — sem isso a saída
> fica em buffer e a rodada parece travada.

### Opções

| Flag | Default | Descrição |
|---|---|---|
| `--models "a,b"` | `harness.config.MODELS` | lista de modelos separada por vírgula |
| `--runs N` | 1 | repetições por modelo |
| `--max-steps N` | 15 | turnos máximos do agente por rodada |
| `--keep-lab` | off | não derruba os containers ao final |
| `--report` | — | só gera `comparison.md` a partir dos transcripts |

---

## Estrutura de pastas

```
harness-tcc/
├── main.py                  # entrypoint (loop serial, sessão, --report)
├── requirements.txt
├── .env                     # chaves (não versionado)
├── README.md
├── harness/                 # pacote da harness
│   ├── config.py            # modelos, timeouts, retries, caminhos
│   ├── env_loader.py        # carrega o .env da raiz
│   ├── agent.py             # system prompt, loop agente, flag, transcript
│   ├── executor.py          # docker compose exec / reset / leitura da flag
│   ├── runner.py            # ciclo de vida do lab + results/ por sessão
│   ├── report.py            # agrega transcripts → comparison.md
│   ├── judge.py             # stub do LLM-as-judge (rubrica + payload)
│   └── llm/
│       ├── __init__.py      # chat(): despacho gemini* → Google, resto → OpenRouter
│       ├── openrouter.py    # cliente OpenRouter (retry, usage/custo)
│       └── google.py        # cliente Gemini via API Chat (retry)
├── results/                 # métricas, transcripts e sessões arquivadas
└── logs/                    # saída das execuções (redirecionada na mão)
```

---

## Arquitetura

```
main.py (entrypoint: loop serial, arquivamento de sessão, --report)
    │
    ├── runner.py ──────── ciclo de vida do lab + results/ (json/md/transcripts)
    │
    └── agent.py ───────── loop agente: resposta → comando → saída → resposta…
            │                 · extrai blocos ```sh das respostas
            │                 · detecta flag (texto FLAG{…} + polling no target)
            │                 · monta transcript (mensagens + comandos + usage)
            │
            ├── llm/__init__.py ── chat(): despacho automático de backend
            │       ├── llm/openrouter.py ── OpenRouter (retry 429/5xx, usage/custo)
            │       └── llm/google.py ────── Gemini via API Chat (retry 429/5xx)
            │
            └── executor.py ─────── docker compose exec attacker (bash -c)
                                    docker compose restart target + /flag/flag.txt
```

| Módulo | Papel |
|---|---|
| `main.py` | CLI, loop serial por modelo/run, arquivamento de sessão, resumo final |
| `harness/config.py` | configuração (modelos, timeouts, retries, caminhos do lab) |
| `harness/env_loader.py` | carrega o `.env` da raiz do projeto |
| `harness/llm/` | clientes LLM com contrato igual: `{message, usage, latency_s}` |
| `harness/agent.py` | prompt do desafio, loop, flag detection, transcript |
| `harness/executor.py` | execução de comandos no `attacker`, reset/leitura da flag |
| `harness/runner.py` | subir/resetar/derrubar lab, salvar transcripts, resumo por sessão |
| `harness/report.py` | agrega todos os transcripts → `comparison.md` |
| `harness/judge.py` | **stub** do LLM-as-judge: rubrica + `build_judge_payload(transcript)` |

### Detalhes importantes

- **Execução no mesmo shell do aluno:** `bash -c` (não `-lc`) para preservar o
  `PATH` com o venv (`/opt/venv`) onde vive o `pymodbus`.
- **Isolamento entre runs:** restart do target a cada rodada → register 0 volta
  a 50 e a flag antiga é apagada da volume `/flag`.
- **Sessão:** ao iniciar, os `results/` anteriores vão para `results/archive-<ts>/`
  (nada é sobrescrito); `comparison.md` varre tudo.
- **Saída com bytes não-UTF-8** não derruba a rodada (`errors="replace"`).

---

## Saídas

```
results/
├── results.json / results.md      # métricas da sessão atual (1 linha por run)
├── comparison.md                  # agregado por modelo (todas as sessões)
├── archive-<ts>/                  # sessões anteriores
└── <modelo>/run-XX/transcript.json  # input pronto p/ o judge
logs/
└── *.log                          # saída das execuções (se redirecionadas)
```

**Métricas por run:** sucesso (flag), tempo até a flag, nº de turnos, nº de
comandos, taxa de erro (exit ≠ 0), tokens (prompt/completion) e custo.

---

## Limitações conhecidos

- **Rate limit:** modelos `:free` do OpenRouter e o Gemini sofrem 429/503;
  o retry/backoff absorve, mas rodadas podem falhar inteiras em picos.
  Serial por isso (1 modelo por vez), com pausa de
  `harness.config.PAUSE_BETWEEN_MODELS`.
- **Custo do Gemini:** a API do Google não retorna preço → `cost_usd` fica 0
  (tokens são registrados normalmente).
- **Judge:** `harness/judge.py` ainda é stub — o transcript já sai no formato
  que ele consome (rubrica em `RUBRIC`, payload via `build_judge_payload`).

---

## Debug

```bash
# Containers
docker compose -f ../probatio-labs/docker-compose.yml ps
docker compose -f ../probatio-labs/docker-compose.yml logs -f target

# Executar um comando no attacker manualmente
docker compose -f ../probatio-labs/docker-compose.yml exec -T attacker bash -c 'hostname'

# Ver a flag atual
docker compose -f ../probatio-labs/docker-compose.yml exec -T target cat /flag/flag.txt
```
