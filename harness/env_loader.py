import os

# Raiz do projeto = diretório que contém o pacote harness/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_dotenv(path=".env"):
    """Carrega variáveis do .env na raiz do projeto (sem dependências externas)."""
    env_path = os.path.join(PROJECT_ROOT, path)
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)
