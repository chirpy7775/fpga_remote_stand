from __future__ import annotations

import os
from collections.abc import Mapping

from django.core.management.base import CommandError

from .models import Agent

AGENT_TOKEN_PREFIX = "AGENT_TOKEN_"


def agent_tokens_from_environ(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ if environ is None else environ
    tokens: dict[str, str] = {}
    for key, value in env.items():
        if not key.startswith(AGENT_TOKEN_PREFIX):
            continue
        name = key[len(AGENT_TOKEN_PREFIX) :].strip()
        token = value.strip()
        if not name or not token:
            continue
        if len(name) > Agent._meta.get_field("name").max_length:
            raise CommandError(f"Слишком длинное имя агента: {name}")
        if len(token) > Agent._meta.get_field("token").max_length:
            raise CommandError(f"Слишком длинный токен у {name}")
        tokens[name] = token
    return tokens


def sync_agents_from_env(environ: Mapping[str, str] | None = None) -> list[str]:
    tokens = agent_tokens_from_environ(environ)
    if not tokens:
        return []

    by_token: dict[str, str] = {}
    for name, token in tokens.items():
        other = by_token.get(token)
        if other is not None:
            raise CommandError(f"Одинаковый токен у {other} и {name}")
        by_token[token] = name

    messages: list[str] = []
    for name, token in tokens.items():
        occupied = Agent.objects.filter(token=token).exclude(name=name).first()
        if occupied is not None:
            raise CommandError(f"Токен для {name} уже занят агентом {occupied.name}")
        agent = Agent.objects.filter(name=name).first()
        if agent is None:
            Agent.objects.create(name=name, token=token)
            messages.append(f"создан {name}")
            continue
        if agent.token != token:
            agent.token = token
            agent.save(update_fields=["token", "updated_at"])
            messages.append(f"обновлён токен {name}")
        else:
            messages.append(f"без изменений {name}")
    return messages
