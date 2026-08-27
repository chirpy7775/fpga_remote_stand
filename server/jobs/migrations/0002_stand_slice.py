import django.db.models.deletion
import jobs.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="job",
            name="claimed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="claimed_jobs",
                to="jobs.agent",
            ),
        ),
        migrations.AddField(
            model_name="job",
            name="instruction",
            field=models.FileField(blank=True, null=True, upload_to=jobs.models.instruction_upload_to),
        ),
        migrations.AddField(
            model_name="job",
            name="instruction_filename",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="job",
            name="target_agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="queued_jobs",
                to="jobs.agent",
            ),
        ),
        migrations.AlterField(
            model_name="job",
            name="error_message",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.CreateModel(
            name="StandSession",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                (
                    "token",
                    models.CharField(default=jobs.models.generate_session_token, editable=False, max_length=64, unique=True),
                ),
                ("started_at", models.DateTimeField()),
                ("ends_at", models.DateTimeField()),
                ("released_at", models.DateTimeField(blank=True, null=True)),
                (
                    "pending_flash",
                    models.FileField(blank=True, null=True, upload_to=jobs.models.session_flash_upload_to),
                ),
                ("pending_flash_name", models.CharField(blank=True, max_length=255)),
                ("pending_commands", models.JSONField(blank=True, default=list)),
                ("pin_states", models.JSONField(default=jobs.models.default_pin_states)),
                (
                    "agent",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to="jobs.agent"),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="stand_sessions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("-started_at",)},
        ),
    ]
