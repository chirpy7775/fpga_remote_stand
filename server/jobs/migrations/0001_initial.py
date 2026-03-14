import django.db.models.deletion
import jobs.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Agent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("token", models.CharField(default=jobs.models.generate_agent_token, editable=False, max_length=64, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Job",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("firmware", models.FileField(upload_to=jobs.models.firmware_upload_to)),
                ("original_filename", models.CharField(max_length=255)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("waiting", "ожидает"),
                            ("running", "выполняется"),
                            ("completed", "завершено"),
                            ("error", "ошибка"),
                        ],
                        default="waiting",
                        max_length=16,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("deadline_at", models.DateTimeField(blank=True, null=True)),
                ("execution_log", models.TextField(blank=True)),
                ("result_video", models.FileField(blank=True, null=True, upload_to=jobs.models.result_video_upload_to)),
                ("error_message", models.CharField(blank=True, max_length=255)),
                (
                    "claimed_by",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="jobs", to="jobs.agent"),
                ),
                (
                    "owner",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="jobs", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
    ]
