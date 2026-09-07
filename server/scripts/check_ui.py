"""Скриншоты ключевых страниц фронтенда через реальный браузер."""
from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

FRONT = "http://127.0.0.1:5173"
OUT = Path("/tmp/uicheck")


def main() -> int:
    OUT.mkdir(exist_ok=True)
    problems: list[str] = []

    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(f"{FRONT}/login", wait_until="networkidle")
        # В сайдбаре есть своя кнопка «Войти», поэтому целимся строго в форму.
        page.fill('input[placeholder="Имя пользователя"]', "admin")
        page.fill('input[type="password"]', "admin123")
        page.click('form button:has-text("Войти")')
        page.wait_for_timeout(2500)
        if "admin" not in page.inner_text("aside"):
            print("вход не выполнен, дальше проверять нечего")
            browser.close()
            return 1
        print("вошли как admin")

        # Маркеры ищем в основной области, а не в сайдбаре: там свои подписи.
        for name, path, marker in [
            ("01_home", "/", "FPGA"),
            ("02_fpga", "/fpga", "стенд"),
            ("03_results", "/results", "заявки"),
            ("04_monitor", "/monitor", "Мониторинг стендов"),
            ("05_docs", "/docs/fpga", "пин"),
        ]:
            page.goto(f"{FRONT}{path}", wait_until="networkidle")
            page.wait_for_timeout(1800)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            body = page.inner_text("main") if page.locator("main").count() else page.inner_text("body")
            if marker.lower() not in body.lower():
                problems.append(f"{path}: не нашёл '{marker}' на странице")
            print(f"{path:<14} снят, {len(body)} символов текста")

        # мониторинг не должен открываться обычному пользователю
        page.goto(f"{FRONT}/", wait_until="networkidle")
        page.click('aside button:has-text("Выйти")')
        page.wait_for_timeout(1500)
        page.goto(f"{FRONT}/monitor", wait_until="networkidle")
        page.wait_for_timeout(1500)
        if "мониторинг стендов" in page.inner_text("body").lower():
            problems.append("/monitor открылся без прав персонала")
        else:
            print("/monitor        закрыт для неавторизованных — ок")
        page.screenshot(path=str(OUT / "06_monitor_denied.png"), full_page=True)

        browser.close()

    if errors:
        print("\nошибки в консоли браузера:")
        for text in dict.fromkeys(errors):
            print("  ", text[:200])
    if problems:
        print("\nпроблемы:")
        for text in problems:
            print("  ", text)
        return 1
    print("\nвсе страницы отрисовались")
    return 0


if __name__ == "__main__":
    sys.exit(main())
