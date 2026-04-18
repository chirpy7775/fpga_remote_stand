#!/usr/bin/env python3
# program_fpga.py – загрузка SVF-файла в MAX 10 через OpenOCD

import subprocess
import sys
import os
import argparse
import time

def main():
    parser = argparse.ArgumentParser(description='Программирование MAX 10 через OpenOCD (SVF)')
    parser.add_argument('svf_file', help='Путь к файлу прошивки в формате SVF (например, demo.svf)')
    parser.add_argument('--config', default='board/max10.cfg',
                        help='Путь к конфигурационному файлу OpenOCD')
    parser.add_argument('--openocd', default='openocd',
                        help='Команда openocd (или полный путь)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Подробный вывод')
    args = parser.parse_args()

    # Проверка существования файлов
    if not os.path.isfile(args.svf_file):
        print(f"Ошибка: файл прошивки '{args.svf_file}' не найден.")
        sys.exit(1)
    if not os.path.isfile(args.config):
        print(f"Ошибка: конфигурационный файл '{args.config}' не найден.")
        sys.exit(1)

    # Команда OpenOCD: загружаем конфиг, выполняем svf, затем exit
    cmd = [
    args.openocd,
    '-f', args.config,
    '-c', 'init',
    '-c', f'svf {args.svf_file}',   # без ignore_error
    '-c', 'shutdown'
    ]

    print(f"Запуск: {' '.join(cmd)}")

    try:
        start = time.time()
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        elapsed = time.time() - start
        if args.verbose:
            print("STDOUT:\n", result.stdout)
            if result.stderr:
                print("STDERR:\n", result.stderr)
        print(f"Прошивка успешно загружена за {elapsed:.2f} сек.")
    except subprocess.CalledProcessError as e:
        print(f"Ошибка OpenOCD (код {e.returncode}):")
        if e.stdout:
            print("STDOUT:\n", e.stdout)
        if e.stderr:
            print("STDERR:\n", e.stderr)
        if "libusb" in e.stderr or "permission" in e.stderr.lower():
            print("\nВозможно, недостаточно прав для USB-Blaster.")
            print("Попробуйте запустить с sudo или проверьте правила udev.")
        sys.exit(e.returncode)

if __name__ == '__main__':
    main()