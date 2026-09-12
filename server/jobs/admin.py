from django.contrib import admin

from .models import Agent, Job, TestbedSession


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "last_seen_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    readonly_fields = ("token", "created_at", "updated_at", "last_seen_at")


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "original_filename",
        "owner",
        "target_agent",
        "status",
        "claimed_by",
        "created_at",
        "deadline_at",
    )
    list_filter = ("status",)
    search_fields = ("original_filename", "owner__username")
    readonly_fields = ("id", "created_at", "updated_at", "started_at", "finished_at")


@admin.register(TestbedSession)
class TestbedSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "agent", "owner", "started_at", "ends_at", "released_at")
    list_filter = ("agent",)
    readonly_fields = ("token", "created_at", "updated_at")
