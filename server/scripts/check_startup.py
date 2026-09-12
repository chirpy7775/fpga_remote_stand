"""Real run.sh + simulation-agent smoke test in a disposable copy; no mocks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
PINS = [2, 3, 4, 5, 6, 9, 10, 11]


def main():
    with tempfile.TemporaryDirectory(prefix="fpga-testbed-startup-") as directory:
        root = Path(directory)
        for name in ("server", "agent"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns(
                ".venv", ".env", "node_modules", "__pycache__", "*.pyc", "*.sqlite3",
                "media", "logs", "workspace", "*.service",
            ))
            (root / name / ".venv").symlink_to(ROOT / name / ".venv", target_is_directory=True)
        server, agent = root / "server", root / "agent"
        python = str(server / ".venv" / "bin" / "python")
        env = os.environ.copy()
        for key in ("AGENT_NAME", "AGENT_TOKEN", "MODE", "SERVER_URL", "DJANGO_SETTINGS_MODULE"):
            env.pop(key, None)
        def manage(*args):
            subprocess.run([python, "manage.py", *args], cwd=server, env=env,
                           check=True, stdout=subprocess.DEVNULL)
        manage("migrate", "--noinput")
        setup = '''
import os
os.environ["DJANGO_SETTINGS_MODULE"] = "remote_testbed.settings"
import django
django.setup()
from django.utils import timezone
from jobs.models import Agent, TestbedSession
from django.contrib.auth.models import User
first = Agent.objects.create(name="testbed-1", token="old-token")
Agent.objects.create(name="testbed-2", token="second-token")
user = User.objects.create(username="migration-user")
TestbedSession.objects.create(agent=first, owner=user, token="preserved-session", ends_at=timezone.now(), released_at=timezone.now())
'''
        subprocess.run([python, "-c", setup], cwd=server, env=env, check=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        (server / ".env").write_text(f"HOST=127.0.0.1\nPORT={port}\nAGENT_NAME=testbed-1\nAGENT_TOKEN=new-token\n")
        (agent / ".env").write_text(f"MODE=simulation\nSERVER_URL={base}\nAGENT_TOKEN=new-token\nPOLL_INTERVAL=1\nGPIO_PINS={','.join(map(str, PINS))}\n")
        processes = []
        def request(path, token=None):
            req = Request(base + path, data=b"" if token else None,
                          headers={"Authorization": f"Token {token}"} if token else {})
            with urlopen(req, timeout=2) as response:
                return json.load(response)
        try:
            with (root / "server-output.log").open("w") as output:
                processes.append(subprocess.Popen(["bash", "run.sh"], cwd=server, env=env,
                                                  stdout=output, stderr=subprocess.STDOUT))
                deadline = time.monotonic() + 30
                while True:
                    try:
                        request("/agent/api/heartbeat/", "new-token")
                        break
                    except (URLError, TimeoutError):
                        if time.monotonic() > deadline or processes[0].poll() is not None:
                            raise RuntimeError((root / "server-output.log").read_text())
                        time.sleep(0.1)
                try:
                    request("/agent/api/heartbeat/", "old-token")
                    raise AssertionError("Old token still accepted")
                except HTTPError as exc:
                    assert exc.code == 401
                with sqlite3.connect(server / "db.sqlite3") as db:
                    assert db.execute("SELECT token FROM jobs_agent WHERE name='testbed-2'").fetchone()[0] == "second-token"
                    assert db.execute("SELECT token FROM jobs_testbedsession").fetchone()[0] == "preserved-session"
                    assert db.execute("SELECT COUNT(*) FROM django_migrations WHERE app='jobs'").fetchone()[0] == 1
                with (root / "agent-output.log").open("w") as agent_output:
                    processes.append(subprocess.Popen(["bash", "run.sh"], cwd=agent, env=env,
                                                      stdout=agent_output, stderr=subprocess.STDOUT))
                    deadline = time.monotonic() + 15
                    while True:
                        rows = request("/api/testbeds/")["testbeds"]
                        row = next(item for item in rows if item["name"] == "testbed-1")
                        if [pin["rpi_bcm"] for pin in row["pin_map"]] == PINS:
                            assert row["online"]
                            break
                        if time.monotonic() > deadline or processes[1].poll() is not None:
                            raise RuntimeError((root / "agent-output.log").read_text())
                        time.sleep(0.1)
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        assert "simulation" in (agent / "logs" / "agent.log").read_text()
        print("PASS: clean database, token rotation, second-agent isolation, session preservation, real simulation heartbeat, custom BCM in API, persistent log")


if __name__ == "__main__":
    main()
