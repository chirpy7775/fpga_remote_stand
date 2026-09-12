from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from jobs.models import Agent


class Command(BaseCommand):
    help = "Creates an agent and prints its token."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--token")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Agent name cannot be empty.")

        token = (options["token"] or "").strip()
        if token and len(token) > Agent._meta.get_field("token").max_length:
            raise CommandError("Agent token is too long.")
        try:
            agent, created = Agent.objects.update_or_create(
                name=name,
                defaults={"token": token} if token else {},
            )
        except IntegrityError as exc:
            raise CommandError("Agent token is already in use.") from exc
        verb = "created" if created else "exists"
        self.stdout.write(f"Agent {verb}: {agent.name}")
        self.stdout.write(f"Token: {agent.token}")
