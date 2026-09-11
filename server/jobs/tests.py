from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .agent_tokens import sync_agents_from_env
from .lite_lang import InstructionError, PinCommand, WriteFrameCommand, parse_instruction
from .models import Agent, Job, StandSession
from .services import JobCompletion, JobService, SessionService


def svf(name="blink.svf", body=b"! SVF stub\n") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, body, content_type="application/octet-stream")


def txt(body="pin 1 high\nwrite_frame 5\n", name="script.txt") -> SimpleUploadedFile:
    return SimpleUploadedFile(name, body.encode("utf-8"), content_type="text/plain")


class LiteLangTests(TestCase):
    def test_parses_pin_and_frames(self):
        commands = parse_instruction("pin 1 high\nwrite_frame 10\npin 1 low\n")
        self.assertEqual(commands[0], PinCommand(pin=1, state="high"))
        self.assertEqual(commands[1], WriteFrameCommand(frames=10))
        self.assertEqual(commands[2], PinCommand(pin=1, state="low"))

    def test_ignores_comments_and_case(self):
        commands = parse_instruction("# comment\n\nPIN 8 HIGH\nWRITE_FRAME 2\n")
        self.assertEqual(commands[0], PinCommand(pin=8, state="high"))
        self.assertEqual(commands[1], WriteFrameCommand(frames=2))

    def test_rejects_unknown_pin(self):
        with self.assertRaises(InstructionError):
            parse_instruction("pin 99 high\n")

    def test_rejects_pin_zero(self):
        with self.assertRaises(InstructionError):
            parse_instruction("pin 0 high\n")

    def test_rejects_bad_state(self):
        with self.assertRaises(InstructionError):
            parse_instruction("pin 1 on\n")

    def test_rejects_unknown_command(self):
        with self.assertRaises(InstructionError):
            parse_instruction("delay 10\n")

    def test_rejects_empty(self):
        with self.assertRaises(InstructionError):
            parse_instruction("# only comment\n")

    def test_rejects_too_many_frames(self):
        with self.assertRaises(InstructionError):
            parse_instruction("write_frame 601\n")

    def test_rejects_non_positive_frames(self):
        with self.assertRaises(InstructionError):
            parse_instruction("write_frame 0\n")


class AgentApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="secret123")
        self.other_user = User.objects.create_user(username="other", password="secret123")
        self.agent = Agent.objects.create(name="stand-1")
        self.agent.touch()
        self.other = Agent.objects.create(name="stand-2")
        self.other.touch()

    def _auth_headers(self, agent: Agent) -> dict:
        return {"HTTP_AUTHORIZATION": f"Token {agent.token}"}

    def test_claim_only_own_jobs(self):
        job = JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        other_job = JobService.create_job(
            owner=self.user, firmware=svf("other.svf"), instruction=txt(), target_agent=self.other
        )
        response = self.client.post(reverse("jobs:agent-next-job"), **self._auth_headers(self.agent))
        self.assertEqual(response.status_code, 200)
        payload = response.json()["job"]
        self.assertEqual(payload["id"], str(job.id))
        self.assertIsNotNone(payload["instruction_url"])

        other_claim = self.client.post(reverse("jobs:agent-next-job"), **self._auth_headers(self.agent))
        self.assertIsNone(other_claim.json()["job"])
        self.assertEqual(Job.objects.get(pk=other_job.pk).status, Job.Status.WAITING)

    def test_invalid_agent_token(self):
        response = self.client.post(
            reverse("jobs:agent-next-job"),
            HTTP_AUTHORIZATION="Token deadbeef",
        )
        self.assertEqual(response.status_code, 401)

    def test_inactive_agent_rejected(self):
        self.agent.is_active = False
        self.agent.save()
        response = self.client.post(reverse("jobs:agent-next-job"), **self._auth_headers(self.agent))
        self.assertEqual(response.status_code, 401)

    def test_session_blocks_claim(self):
        JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        SessionService.take(user=self.user, agent=self.agent, duration_seconds=120)
        response = self.client.post(reverse("jobs:agent-next-job"), **self._auth_headers(self.agent))
        self.assertIsNone(response.json()["job"])
        self.assertEqual(Job.objects.filter(status=Job.Status.WAITING).count(), 1)

    def test_complete_job_and_download_instruction(self):
        job = JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        claimed = JobService.claim_next_job(agent=self.agent)
        self.assertEqual(claimed.id, job.id)
        instruction = self.client.get(
            reverse("jobs:agent-job-instruction", kwargs={"job_id": job.id}),
            **self._auth_headers(self.agent),
        )
        self.assertEqual(instruction.status_code, 200)
        firmware = self.client.get(
            reverse("jobs:agent-job-firmware", kwargs={"job_id": job.id}),
            **self._auth_headers(self.agent),
        )
        self.assertEqual(firmware.status_code, 200)

        done = JobService.complete_job(
            job=job,
            agent=self.agent,
            completion=JobCompletion(status=Job.Status.COMPLETED, execution_log="ok"),
        )
        self.assertEqual(done.status, Job.Status.COMPLETED)

    def test_other_agent_cannot_download_firmware(self):
        job = JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        JobService.claim_next_job(agent=self.agent)
        response = self.client.get(
            reverse("jobs:agent-job-firmware", kwargs={"job_id": job.id}),
            **self._auth_headers(self.other),
        )
        self.assertEqual(response.status_code, 404)

    def test_rejects_non_svf(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf("blink.bin", b"xx"), "instruction": txt()},
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_non_txt_instruction(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("jobs:api-jobs"),
            {
                "target_agent": self.agent.id,
                "firmware": svf(),
                "instruction": SimpleUploadedFile("script.md", b"pin 1 high\n"),
            },
        )
        self.assertEqual(response.status_code, 400)

    def test_rejects_broken_instruction(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf(), "instruction": txt("pin 1 maybe\n")},
        )
        self.assertEqual(response.status_code, 400)

    def test_jobs_are_isolated_per_user(self):
        job = JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        self.client.force_login(self.other_user)
        listed = self.client.get(reverse("jobs:api-jobs"))
        self.assertEqual(listed.json()["jobs"], [])
        detail = self.client.get(reverse("jobs:api-job-detail", kwargs={"pk": job.id}))
        self.assertEqual(detail.status_code, 404)

    def test_unauthenticated_session_blocked(self):
        self.assertEqual(self.client.get(reverse("jobs:api-session")).status_code, 401)
        self.assertEqual(
            self.client.post(reverse("jobs:api-take-stand", kwargs={"pk": self.agent.id})).status_code,
            401,
        )


class AuthApiTests(TestCase):
    def test_register_login_me_logout(self):
        created = self.client.post(
            reverse("jobs:api-register"),
            data={"username": "alice", "password": "pw12345", "email": "a@a.a"},
            content_type="application/json",
        )
        self.assertEqual(created.status_code, 201)
        me = self.client.get(reverse("jobs:api-me"))
        self.assertEqual(me.json()["user"]["username"], "alice")
        self.client.post(reverse("jobs:api-logout"))
        self.assertIsNone(self.client.get(reverse("jobs:api-me")).json()["user"])
        bad = self.client.post(
            reverse("jobs:api-login"),
            data={"username": "alice", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post(
            reverse("jobs:api-login"),
            data={"username": "alice", "password": "pw12345"},
            content_type="application/json",
        )
        self.assertEqual(ok.status_code, 200)

    def test_duplicate_register(self):
        payload = {"username": "alice", "password": "pw12345"}
        self.client.post(reverse("jobs:api-register"), data=payload, content_type="application/json")
        again = self.client.post(reverse("jobs:api-register"), data=payload, content_type="application/json")
        self.assertEqual(again.status_code, 400)

    def test_me_reports_anonymous_flag(self):
        response = self.client.get(reverse("jobs:api-me"))
        self.assertIsNone(response.json()["user"])
        self.assertTrue(response.json()["allow_anonymous"])


class GuestJobTests(TestCase):
    def setUp(self):
        self.agent = Agent.objects.create(name="stand-1")
        self.agent.touch()

    def test_guest_can_submit_and_list_own_jobs(self):
        created = self.client.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf(), "instruction": txt()},
        )
        self.assertEqual(created.status_code, 201)
        job_id = created.json()["job"]["id"]
        listed = self.client.get(reverse("jobs:api-jobs"))
        self.assertEqual([job["id"] for job in listed.json()["jobs"]], [job_id])
        detail = self.client.get(reverse("jobs:api-job-detail", kwargs={"pk": job_id}))
        self.assertEqual(detail.status_code, 200)

    def test_guest_jobs_are_isolated_by_cookie(self):
        first = Client()
        second = Client()
        created = first.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf(), "instruction": txt()},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(second.get(reverse("jobs:api-jobs")).json()["jobs"], [])

    def test_guest_cannot_take_session(self):
        response = self.client.post(reverse("jobs:api-take-stand", kwargs={"pk": self.agent.id}))
        self.assertEqual(response.status_code, 401)

    @override_settings(ALLOW_ANON_JOB_SUBMISSION=False)
    def test_guest_blocked_when_disabled(self):
        self.assertEqual(self.client.get(reverse("jobs:api-stands")).status_code, 401)
        self.assertEqual(self.client.get(reverse("jobs:api-jobs")).status_code, 401)
        created = self.client.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf(), "instruction": txt()},
        )
        self.assertEqual(created.status_code, 401)


class SessionLockTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="student", password="secret123")
        self.other_user = User.objects.create_user(username="other", password="secret123")
        self.agent = Agent.objects.create(name="stand-1")
        self.agent.touch()
        self.other_agent = Agent.objects.create(name="stand-2")
        self.other_agent.touch()

    def test_exclusive_lock(self):
        session = SessionService.take(user=self.user, agent=self.agent, duration_seconds=120)
        self.assertTrue(session.is_active)
        with self.assertRaises(ValueError):
            SessionService.take(user=self.other_user, agent=self.agent, duration_seconds=120)

    def test_user_cannot_hold_two_sessions(self):
        SessionService.take(user=self.user, agent=self.agent, duration_seconds=120)
        with self.assertRaises(ValueError):
            SessionService.take(user=self.user, agent=self.other_agent, duration_seconds=120)

    def test_offline_stand_rejected(self):
        offline = Agent.objects.create(name="dead")
        with self.assertRaises(ValueError):
            SessionService.take(user=self.user, agent=offline, duration_seconds=120)

    def test_running_job_blocks_session(self):
        JobService.create_job(
            owner=self.user, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        JobService.claim_next_job(agent=self.agent)
        with self.assertRaises(ValueError):
            SessionService.take(user=self.other_user, agent=self.agent, duration_seconds=120)

    def test_heartbeat_and_session_poll(self):
        SessionService.take(user=self.user, agent=self.agent, duration_seconds=120)
        SessionService.enqueue_pin(session=StandSession.objects.get(owner=self.user), pin=3, state="high")
        response = self.client.post(
            reverse("jobs:agent-heartbeat"),
            HTTP_AUTHORIZATION=f"Token {self.agent.token}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["has_session"])

        poll = self.client.get(
            reverse("jobs:agent-session"),
            HTTP_AUTHORIZATION=f"Token {self.agent.token}",
        )
        commands = poll.json()["session"]["commands"]
        self.assertEqual(commands[0]["pin"], 3)
        second = self.client.get(
            reverse("jobs:agent-session"),
            HTTP_AUTHORIZATION=f"Token {self.agent.token}",
        )
        self.assertEqual(second.json()["session"]["commands"], [])

    def test_pin_and_flash_api(self):
        self.client.force_login(self.user)
        taken = self.client.post(
            reverse("jobs:api-take-stand", kwargs={"pk": self.agent.id}),
            data={"duration_seconds": 180},
            content_type="application/json",
        )
        self.assertEqual(taken.status_code, 201)
        pin = self.client.post(
            reverse("jobs:api-session-pin"),
            data={"pin": 8, "state": "high"},
            content_type="application/json",
        )
        self.assertEqual(pin.status_code, 200)
        self.assertTrue(pin.json()["session"]["pin_states"][7])

        bad_pin = self.client.post(
            reverse("jobs:api-session-pin"),
            data={"pin": 9, "state": "high"},
            content_type="application/json",
        )
        self.assertEqual(bad_pin.status_code, 400)

        flash = self.client.post(
            reverse("jobs:api-session-flash"),
            {"flash_file": svf("live.svf")},
        )
        self.assertEqual(flash.status_code, 200)
        self.assertEqual(flash.json()["session"]["pending_flash_name"], "live.svf")

        bad_flash = self.client.post(
            reverse("jobs:api-session-flash"),
            {"flash_file": svf("nope.bin", b"xx")},
        )
        self.assertEqual(bad_flash.status_code, 400)

        released = self.client.post(reverse("jobs:api-session-release"))
        self.assertEqual(released.status_code, 200)
        after = self.client.get(reverse("jobs:api-session"))
        self.assertIsNone(after.json()["session"])

    def test_pin_without_session(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("jobs:api-session-pin"),
            data={"pin": 1, "state": "high"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    def test_expired_session_is_released(self):
        session = SessionService.take(user=self.user, agent=self.agent, duration_seconds=120)
        StandSession.objects.filter(pk=session.pk).update(ends_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(SessionService.expire_sessions(), 1)
        self.assertIsNone(SessionService.active_for_user(self.user))


class SyncAgentsTests(TestCase):
    def test_creates_and_updates_from_env(self):
        messages = sync_agents_from_env({"AGENT_TOKEN_stand-1": "token-one"})
        self.assertEqual(messages, ["создан stand-1"])
        agent = Agent.objects.get(name="stand-1")
        self.assertEqual(agent.token, "token-one")

        messages = sync_agents_from_env({"AGENT_TOKEN_stand-1": "token-two"})
        self.assertEqual(messages, ["обновлён токен stand-1"])
        agent.refresh_from_db()
        self.assertEqual(agent.token, "token-two")

        messages = sync_agents_from_env({"AGENT_TOKEN_stand-1": "token-two"})
        self.assertEqual(messages, ["без изменений stand-1"])

    def test_rejects_duplicate_tokens(self):
        with self.assertRaises(CommandError):
            sync_agents_from_env(
                {"AGENT_TOKEN_stand-1": "same", "AGENT_TOKEN_stand-2": "same"}
            )

    def test_rejects_token_owned_by_another_agent(self):
        Agent.objects.create(name="stand-1", token="taken")
        with self.assertRaises(CommandError):
            sync_agents_from_env({"AGENT_TOKEN_stand-2": "taken"})


class MonitorApiTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username="admin", password="pw12345", is_staff=True)
        self.student = User.objects.create_user(username="student", password="pw12345")
        self.agent = Agent.objects.create(name="stand-1")
        self.agent.touch()

    def test_requires_staff(self):
        url = reverse("jobs:api-monitor-overview")
        self.assertEqual(self.client.get(url).status_code, 401)
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_overview_reports_who_uploads_and_who_holds_the_stand(self):
        JobService.create_job(
            owner=self.student, firmware=svf("mine.svf"), instruction=txt(), target_agent=self.agent
        )
        SessionService.take(user=self.student, agent=self.agent, duration_seconds=300)

        self.client.force_login(self.staff)
        payload = self.client.get(reverse("jobs:api-monitor-overview")).json()

        self.assertEqual(payload["totals"]["active_sessions"], 1)
        self.assertEqual(payload["totals"]["waiting_jobs"], 1)
        self.assertEqual(payload["jobs"][0]["owner"], "student")
        self.assertEqual(payload["jobs"][0]["original_filename"], "mine.svf")
        self.assertIsNotNone(payload["jobs"][0]["firmware_url"])

        stand = payload["stands"][0]
        self.assertEqual(stand["name"], "stand-1")
        self.assertEqual(stand["current_session"]["owner"], "student")
        self.assertIsNone(stand["current_job"])

    def test_overview_marks_guest_uploads(self):
        self.client.post(
            reverse("jobs:api-jobs"),
            {"target_agent": self.agent.id, "firmware": svf(), "instruction": txt()},
        )
        self.client.force_login(self.staff)
        job = self.client.get(reverse("jobs:api-monitor-overview")).json()["jobs"][0]
        self.assertTrue(job["is_guest"])
        self.assertEqual(job["owner"], "гость")

    def test_overview_shows_running_job_on_the_stand(self):
        JobService.create_job(
            owner=self.student, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        JobService.claim_next_job(agent=self.agent)
        self.client.force_login(self.staff)
        payload = self.client.get(reverse("jobs:api-monitor-overview")).json()
        self.assertEqual(payload["totals"]["running_jobs"], 1)
        self.assertEqual(payload["stands"][0]["current_job"]["owner"], "student")

    def test_job_detail_returns_full_log(self):
        job = JobService.create_job(
            owner=self.student, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        JobService.claim_next_job(agent=self.agent)
        JobService.complete_job(
            job=job,
            agent=self.agent,
            completion=JobCompletion(status=Job.Status.COMPLETED, execution_log="строка лога"),
        )
        self.client.force_login(self.staff)
        detail = self.client.get(reverse("jobs:api-monitor-job", kwargs={"pk": job.id}))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["job"]["execution_log"], "строка лога")

    def test_job_detail_denied_for_students(self):
        job = JobService.create_job(
            owner=self.student, firmware=svf(), instruction=txt(), target_agent=self.agent
        )
        self.client.force_login(self.student)
        detail = self.client.get(reverse("jobs:api-monitor-job", kwargs={"pk": job.id}))
        self.assertEqual(detail.status_code, 403)

    def test_me_exposes_staff_flag(self):
        self.client.force_login(self.staff)
        self.assertTrue(self.client.get(reverse("jobs:api-me")).json()["user"]["is_staff"])
        self.client.force_login(self.student)
        self.assertFalse(self.client.get(reverse("jobs:api-me")).json()["user"]["is_staff"])


class LegacyHtmlRemovedTests(TestCase):
    def test_old_pages_are_gone(self):
        self.assertEqual(self.client.get("/dashboard/").status_code, 404)
        self.assertEqual(self.client.get("/start/").status_code, 404)
        self.assertEqual(self.client.get("/accounts/login/").status_code, 404)

    def test_root_redirects_to_frontend(self):
        from pathlib import Path

        from django.conf import settings

        response = self.client.get("/")
        dist = Path(settings.BASE_DIR) / "frontend" / "dist" / "index.html"
        if dist.is_file():
            self.assertEqual(response.status_code, 200)
        else:
            self.assertEqual(response.status_code, 302)
            self.assertTrue(response.url.startswith("http://127.0.0.1:5173"))
