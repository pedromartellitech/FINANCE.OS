"""Inicia a instalação local ou uma demonstração independente."""

import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Finance OS · Pedro Martelli")
    parser.add_argument(
        "--demo", action="store_true", help="Usar somente dados fictícios e temporários"
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="Não abrir o navegador automaticamente"
    )
    parser.add_argument("--port", type=int, default=8501, help="Porta local (padrão: 8501)")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Use uma porta entre 1024 e 65535.")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            parser.error("A porta está ocupada. Use --port com outra porta.")
    root = Path(__file__).resolve().parent
    env = os.environ.copy()
    if args.demo:
        env["FINANCE_OS_DEMO_ONLY"] = "1"
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(root / "app.py"),
        "--server.address=127.0.0.1",
        f"--server.port={args.port}",
        "--server.headless=true",
    ]
    process = subprocess.Popen(command, cwd=root, env=env)
    try:
        if not args.no_browser:
            for _ in range(80):
                if process.poll() is not None:
                    break
                with socket.socket() as check:
                    if check.connect_ex(("127.0.0.1", args.port)) == 0:
                        webbrowser.open(f"http://127.0.0.1:{args.port}")
                        break
                time.sleep(0.1)
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
