#!/usr/bin/env python
import os
import sys

from remote_stand.env import load_env


def main() -> None:
    load_env()
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "remote_stand.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError("Django is not installed.") from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
