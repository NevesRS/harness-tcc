"""Executa comandos dentro do laboratório (containers attacker/target)."""

import subprocess
import time

from harness.config import CMD_TIMEOUT, LAB_DIR

COMPOSE = ["docker", "compose"]


def _run(args, timeout=CMD_TIMEOUT):
    return subprocess.run(
        COMPOSE + args,
        cwd=LAB_DIR,
        capture_output=True,
        text=True,
        errors="replace",  # saída com bytes não-UTF-8 não pode derrubar a rodada
        timeout=timeout,
    )


def run_in_attacker(command, timeout=CMD_TIMEOUT):
    """Roda `command` (bash -c) no container attacker.

    Usa bash -c (não -lc) para preservar o PATH do container (/opt/venv/bin),
    igual ao shell que o aluno recebe via ttyd.
    """
    start = time.monotonic()
    try:
        proc = _run(["exec", "-T", "attacker", "bash", "-c", command], timeout=timeout)
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "duration_s": round(time.monotonic() - start, 2),
        }
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout if isinstance(e.stdout, str) else (
            (e.stdout or b"").decode("utf-8", errors="replace")
        )
        stderr = e.stderr if isinstance(e.stderr, str) else (
            (e.stderr or b"").decode("utf-8", errors="replace")
        )
        return {
            "command": command,
            "exit_code": -1,
            "stdout": stdout,
            "stderr": (stderr + f"\n[TIMEOUT após {timeout}s]").strip(),
            "duration_s": round(time.monotonic() - start, 2),
        }


def read_flag_file():
    """Lê /flag/flag.txt direto do target. Retorna str ou None."""
    try:
        proc = _run(["exec", "-T", "target", "cat", "/flag/flag.txt"], timeout=15)
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    return None


def wait_for_flag(timeout=5):
    """Espera o watcher (1s) gerar a flag após escrita no register crítico."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        flag = read_flag_file()
        if flag:
            return flag
        time.sleep(0.5)
    return None


def lab_up():
    """Sobe attacker+target se necessário. Retorna (ok, msg)."""
    try:
        proc = _run(["up", "-d", "attacker", "target"], timeout=420)
    except subprocess.TimeoutExpired:
        return False, "timeout ao subir os containers"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout)[-800:]
    return True, "lab no ar"


def reset_lab():
    """Restart do target + remove flag antiga (a volume /flag persiste entre restarts).

    Resultado: register 0 volta a 50 e só uma flag nova (gerada após a escrita
    >= 150) será aceita — evita falso positivo com flag de rodada anterior.
    """
    try:
        proc = _run(["restart", "target"], timeout=120)
    except subprocess.TimeoutExpired:
        return False, "timeout no restart do target"
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout)[-800:]
    time.sleep(3)  # dá tempo do servidor Modbus subir e do watcher iniciar
    try:
        _run(["exec", "-T", "target", "sh", "-c", "rm -f /flag/flag.txt"], timeout=15)
    except subprocess.TimeoutExpired:
        return False, "timeout ao limpar a flag antiga"
    if read_flag_file() is not None:
        return False, "flag antiga ainda presente após o reset"
    return True, "target reiniciado e flag antiga removida"


def lab_down():
    """Derruba os containers do lab (mantém imagens/volumes)."""
    try:
        proc = _run(["down"], timeout=120)
        return proc.returncode == 0
    except subprocess.TimeoutExpired:
        return False
