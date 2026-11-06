import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from toolkit.api import create_app

ROOT = Path(__file__).resolve().parents[2]
HEADERS = {"X-Toolkit-Request": "1"}

@contextmanager
def server(module, env=None, port=None):
    if port is None:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
    command = [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--no-access-log", "--log-level", "error"]
    if module.endswith("create_app"):
        command.append("--factory")
    process = subprocess.Popen(command, cwd=ROOT, env={**os.environ, **(env or {})}, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    url = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(trust_env=False, timeout=.5) as client:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError(process.communicate()[1].decode())
                try:
                    response = client.get(url + ("/api/settings" if module.endswith("create_app") else "/health"))
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(.05)
            else:
                raise RuntimeError("Server did not start")
        yield url, process
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

@pytest.fixture(scope="session")
def upstream():
    with server("toolkit.demo:app") as (url, _):
        yield url

@pytest.fixture
def client(tmp_path, upstream):
    httpx.post(upstream + "/reset", trust_env=False)
    app = create_app(tmp_path / "test.db", upstream)
    with TestClient(app, headers=HEADERS) as client:
        yield client


def wait_run(client, run_id, expected=None, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get("/api/runs/" + run_id)
        assert response.status_code == 200, response.text
        run = response.json()
        if run["status"] != "running":
            if expected:
                assert run["status"] == expected, run
            return run
        time.sleep(.025)
    raise AssertionError("Run did not finish")


def start(client, scenario="healthy", full=False):
    response = client.post("/api/runs", json={"scenario": scenario, "full": full})
    assert response.status_code == 202, response.text
    return response.json()["id"]
