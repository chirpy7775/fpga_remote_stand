from django.core.management.base import BaseCommand

from jobs.agent_tokens import sync_agents_from_env


class Command(BaseCommand):
    help = "Создаёт и обновляет агентов из переменных AGENT_TOKEN_*."

    def handle(self, *args, **options):
        messages = sync_agents_from_env()
        if not messages:
            self.stdout.write("В окружении нет AGENT_TOKEN_* — агенты не тронуты.")
            return
        for line in messages:
            self.stdout.write(line)
