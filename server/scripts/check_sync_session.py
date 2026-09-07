"""Ручная проверка синхронной сессии на живом стенде.

Берёт стенд, смотрит живой стрим, дёргает пины, шьёт SVF в сессии, отпускает.
Кадры складывает в /tmp/synccheck.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import requests
import websocket

BASE = "http://127.0.0.1:8000"
OUT = Path("/tmp/synccheck")
STAND_ID = 1


def login(username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.get(f"{BASE}/api/auth/csrf/", timeout=10)
    token = session.cookies["csrftoken"]
    response = session.post(
        f"{BASE}/api/auth/login/",
        json={"username": username, "password": password},
        headers={"X-CSRFToken": token, "Referer": BASE},
        timeout=10,
    )
    response.raise_for_status()
    return session


def csrf(session: requests.Session) -> dict:
    return {"X-CSRFToken": session.cookies["csrftoken"], "Referer": BASE}


def grab(viewer: websocket.WebSocket, label: str, seconds: float = 3.0) -> int:
    """Копит кадры заданное время, сохраняет последний."""
    deadline = time.monotonic() + seconds
    last, count = None, 0
    while time.monotonic() < deadline:
        try:
            frame = viewer.recv()
        except websocket.WebSocketTimeoutException:
            continue
        if isinstance(frame, bytes) and frame:
            last, count = frame, count + 1
    if last:
        kind = "jpg" if last[:2] == b"\xff\xd8" else "png" if last[:4] == b"\x89PNG" else "bin"
        path = OUT / f"{label}.{kind}"
        path.write_bytes(last)
        print(f"  {label}: {count} кадров, последний {len(last)} Б -> {path.name}")
    else:
        print(f"  {label}: кадров не получено")
    return count


def main() -> int:
    OUT.mkdir(exist_ok=True)
    client = login("admin", "admin123")

    taken = client.post(
        f"{BASE}/api/stands/{STAND_ID}/take/",
        json={"duration_seconds": 300},
        headers=csrf(client),
        timeout=10,
    )
    if taken.status_code != 201:
        print("не удалось занять стенд:", taken.status_code, taken.text[:200])
        return 1
    session_token = taken.json()["session"]["token"]
    print("сессия открыта, токен получен")

    try:
        print("ждём, пока агент поднимет стрим...")
        time.sleep(6)
        viewer = websocket.create_connection(
            f"ws://127.0.0.1:8000/ws/camera/viewer/?token={session_token}", timeout=8
        )
        print("вьюер подключён")

        results = {}
        results["idle"] = grab(viewer, "01_idle")

        for pin in (1, 8):
            client.post(
                f"{BASE}/api/session/pin/",
                json={"pin": pin, "state": "high"},
                headers=csrf(client),
                timeout=10,
            )
            results[f"pin{pin}"] = grab(viewer, f"02_pin{pin}_high")

        for pin in range(1, 9):
            client.post(
                f"{BASE}/api/session/pin/",
                json={"pin": pin, "state": "high"},
                headers=csrf(client),
                timeout=10,
            )
        results["all"] = grab(viewer, "03_all_high")

        for pin in range(1, 9):
            client.post(
                f"{BASE}/api/session/pin/",
                json={"pin": pin, "state": "low"},
                headers=csrf(client),
                timeout=10,
            )
        results["off"] = grab(viewer, "04_all_low")

        state = client.get(f"{BASE}/api/session/", timeout=10).json()["session"]
        print("пины по мнению сервера:", state["pin_states"])

        svf = Path(__file__).resolve().parents[1] / "examples" / "gpio_led_test.svf"
        with svf.open("rb") as handle:
            flashed = client.post(
                f"{BASE}/api/session/flash/",
                files={"flash_file": (svf.name, handle, "application/octet-stream")},
                headers=csrf(client),
                timeout=60,
            )
        print("прошивка в сессии:", flashed.status_code, flashed.json()["session"]["pending_flash_name"])
        results["after_flash"] = grab(viewer, "05_after_flash", seconds=20)

        viewer.close()
        print("\nитог по кадрам:", results)
        return 0 if all(count > 0 for count in results.values()) else 1
    finally:
        client.post(f"{BASE}/api/session/release/", headers=csrf(client), timeout=10)
        print("сессия отпущена")


if __name__ == "__main__":
    sys.exit(main())
