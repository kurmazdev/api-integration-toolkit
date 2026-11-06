#!/usr/bin/env python3
"""Run the two loopback APIs, plus optional Vite. No process manager required."""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true", help="Start Vite on 5173 for hot reload")
    args = parser.parse_args()
    os.chdir(ROOT)
    os.umask(0o077)
    if not args.dev and not (ROOT / "frontend/dist/index.html").exists():
        sys.exit("Build the UI first: npm --prefix frontend run build")
    for port in ([8000, 8001, 5173] if args.dev else [8000, 8001]):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                sys.exit(f"Port {port} is already in use. Stop the existing process before starting the toolkit.")
    commands = [
        [sys.executable, "-m", "uvicorn", "toolkit.demo:app", "--host", "127.0.0.1", "--port", "8001", "--no-access-log"],
        [sys.executable, "-m", "uvicorn", "toolkit.api:create_app", "--factory", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"],
    ]
    if args.dev:
        commands.append(["npm", "--prefix", "frontend", "run", "dev"])
    children = []
    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    print("Integration Toolkit → http://127.0.0.1:" + ("5173" if args.dev else "8000"), flush=True)
    try:
        for command in commands:
            children.append(subprocess.Popen(command, start_new_session=os.name == "posix"))
        while all(child.poll() is None for child in children):
            time.sleep(.3)
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            if child.poll() is None:
                if os.name == "posix":
                    os.killpg(child.pid, signal.SIGTERM)
                else:
                    child.terminate()
        for child in children:
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
    return next((child.returncode for child in children if child.returncode not in (0, -15)), 0)

if __name__ == "__main__":
    sys.exit(main())
