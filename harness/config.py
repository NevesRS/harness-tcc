import os

from harness.env_loader import load_dotenv

load_dotenv()

# --- OpenRouter ---
API_URL = "https://openrouter.ai/api/v1/chat/completions"
API_KEY = (os.environ.get("OPENROUTER_API_KEY") or "").strip()

REQUEST_TIMEOUT = 180  # segundos
MAX_RETRIES = 6
RETRY_STATUS = {429, 500, 502, 503, 504}

# --- Harness ---
MODELS = ["nvidia/nemotron-3-ultra-550b-a55b:free"]
MAX_STEPS = 15          # turnos máximos do agente por modelo
CMD_TIMEOUT = 60        # timeout (s) por comando executado no attacker
MAX_OUTPUT_CHARS = 4000  # corte da saída devolvida ao modelo
PAUSE_BETWEEN_MODELS = 15  # pausa serial entre modelos (rate limit dos :free)

# --- Laboratório (probatio-labs) ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "probatio-labs")
LAB_SUBNET = "172.28.0.0/24"
TARGET_IP = "172.28.0.20"
ATTACKER_IP = "172.28.0.10"

RESULTS_DIR = os.path.join(PROJECT_ROOT, "results")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
