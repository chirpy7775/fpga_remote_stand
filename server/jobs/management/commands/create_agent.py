from django.core.management.base import BaseCommand, CommandError

from jobs.models import Agent


class Command(BaseCommand):
    help = "Creates an agent and prints its token."

    def add_arguments(self, parser):
        parser.add_argument("name")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Agent name cannot be empty.")

        agent, created = Agent.objects.get_or_create(name=name)
        verb = "created" if created else "exists"
        self.stdout.write(f"Agent {verb}: {agent.name}")
        self.stdout.write(f"Token: {agent.token}")
