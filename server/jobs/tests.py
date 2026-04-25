from __future__ import annotations

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Job


@override_settings(ALLOW_ANON_JOB_SUBMISSION=False)
class AnonymousSubmissionToggleTests(TestCase):
    def test_continue_as_guest_is_blocked_when_disabled(self):
        response = self.client.post(reverse("jobs:continue-as-guest"), follow=True)

        self.assertRedirects(response, reverse("jobs:start"))
        self.assertContains(response, "Гостевой режим отключен в конфигурации сервера.")

    def test_guest_dashboard_is_blocked_when_disabled(self):
        response = self.client.get(reverse("jobs:dashboard"), follow=True)

        self.assertRedirects(response, reverse("jobs:start"))
        self.assertContains(response, "Анонимная отправка заданий отключена.")

    def test_authenticated_user_can_submit_job_when_disabled(self):
        user = User.objects.create_user(username="student", password="secret123")
        self.client.force_login(user)

        firmware = SimpleUploadedFile("blink.bin", b"\x00\x01\x02", content_type="application/octet-stream")
        response = self.client.post(
            reverse("jobs:dashboard"),
            {"firmware": firmware},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Job.objects.filter(owner=user).count(), 1)
