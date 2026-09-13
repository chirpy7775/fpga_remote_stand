from __future__ import annotations

import unittest
import unittest.mock
from pathlib import Path
from tempfile import TemporaryDirectory

from remote_agent.hardware import (
    HardwareExecutor,
    ProgramResult,
    StubCamera,
    StubGpio,
)
from remote_agent.config import AgentConfig
from remote_agent.hardware_real import RealProgrammer, _MjpegPipe
from remote_agent.lite_lang import InstructionError, parse_instruction

# Часть проверок сверяет агента с серверной частью репозитория. На самом стенде
# развёрнут только каталог agent/, поэтому такие тесты там пропускаются.
REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_CONSTANTS = REPO_ROOT / "server" / "jobs" / "constants.py"
EXAMPLE_SCRIPT = REPO_ROOT / "server" / "examples" / "de10_lite" / "gpio_test" / "gpio_test.txt"


class LoggingTests(unittest.TestCase):
    def test_file_log_survives_shutdown_and_rotates(self):
        import logging
        import os
        from remote_agent.__main__ import main
        from logging.handlers import RotatingFileHandler

        with TemporaryDirectory() as directory:
            path = Path(directory) / "logs" / "agent.log"
            with unittest.mock.patch.dict(os.environ, {"LOG_FILE": str(path), "MODE": "invalid"}), \
                    unittest.mock.patch("remote_agent.__main__.load_env"), \
                    unittest.mock.patch("logging.basicConfig") as configure:
                self.assertEqual(main(), 2)
            handlers = configure.call_args.kwargs["handlers"]
            handler = next(item for item in handlers if isinstance(item, RotatingFileHandler))
            try:
                self.assertEqual(handler.maxBytes, 5 * 1024 * 1024)
                self.assertEqual(handler.backupCount, 3)
                handler.emit(logging.LogRecord("agent", logging.INFO, "", 0, "x" * handler.maxBytes, (), None))
                handler.emit(logging.LogRecord("agent", logging.INFO, "", 0, "after rotation", (), None))
            finally:
                for item in handlers:
                    item.close()
            self.assertIn("after rotation", path.read_text())
            self.assertTrue(Path(str(path) + ".1").exists())


class FakeProgrammer:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.calls: list[Path] = []

    def program(self, firmware_path: Path) -> ProgramResult:
        self.calls.append(firmware_path)
        return ProgramResult(ok=self.ok, log=["fake programmer"])


class RecordingCamera:
    """Камера, которая только считает, что её просили сделать."""

    fps = 10

    def __init__(self) -> None:
        self.started = 0
        self.held: list[tuple[int, list[bool]]] = []
        self.stopped = 0
        self.closed = 0
        self.pins_at_stop: list[bool] | None = None
        # Необязательный доступ к GPIO, чтобы поймать момент stop_recording.
        self.gpio_probe = None

    def start_recording(self) -> list[str]:
        self.started += 1
        return ["start"]

    def hold_frames(self, frames: int, pins: list[bool]) -> None:
        self.held.append((frames, list(pins)))

    def stop_recording(self, video_path: Path) -> list[str]:
        self.stopped += 1
        self.pins_at_stop = list(self.gpio_probe()) if self.gpio_probe else None
        video_path.write_bytes(b"video")
        return ["stop"]

    def live_frame(self, pins: list[bool]) -> bytes | None:
        return b"frame"

    def close(self) -> None:
        self.closed += 1


class ExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        self.firmware = self.workspace / "test.svf"
        self.firmware.write_text("! svf\n")
        self.addCleanup(self.tmp.cleanup)

    def _run(self, script: str, programmer=None, camera=None, gpio=None, timeout=60):
        self.programmer = programmer or FakeProgrammer()
        self.camera = camera or RecordingCamera()
        self.gpio = gpio or StubGpio()
        executor = HardwareExecutor(
            programmer=self.programmer, camera=self.camera, gpio=self.gpio
        )
        return executor.run(
            firmware_path=self.firmware,
            instruction_text=script,
            workspace=self.workspace,
            timeout_seconds=timeout,
        )

    def test_runs_script_and_records_video(self):
        result = self._run("pin 1 high\nwrite_frame 5\npin 1 low\nwrite_frame 5\n")
        self.assertEqual(result.status, "completed")
        self.assertEqual(self.camera.started, 1)
        self.assertEqual(self.camera.stopped, 1)
        self.assertEqual([frames for frames, _ in self.camera.held], [5, 5])
        # первый write_frame снят при поднятом пине 1, второй — при опущенном
        self.assertTrue(self.camera.held[0][1][0])
        self.assertFalse(self.camera.held[1][1][0])

    def test_bad_script_does_not_touch_the_board(self):
        result = self._run("pin 1 sideways\n")
        self.assertEqual(result.status, "error")
        self.assertEqual(self.programmer.calls, [], "плату нельзя шить при битом сценарии")
        self.assertEqual(self.camera.started, 0)

    def test_failed_programming_stops_before_script(self):
        result = self._run("write_frame 5\n", programmer=FakeProgrammer(ok=False))
        self.assertEqual(result.status, "error")
        self.assertIn("Прошивка не удалась", result.error_message)
        self.assertEqual(self.camera.started, 0)

    def test_script_without_write_frame_still_records(self):
        result = self._run("pin 2 high\n")
        self.assertEqual(result.status, "completed")
        self.assertEqual(len(self.camera.held), 1)
        self.assertGreater(self.camera.held[0][0], 0)

    def test_pins_are_released_after_job(self):
        gpio = StubGpio()
        self._run("pin 3 high\nwrite_frame 2\n", gpio=gpio)
        self.assertEqual(gpio.snapshot(), [False] * 8, "линии обязаны сняться после задачи")

    def test_pins_are_released_before_video_is_encoded(self):
        """Перекодирование долгое — плату нельзя держать под напряжением всё это время."""
        gpio = StubGpio()
        camera = RecordingCamera()
        camera.gpio_probe = gpio.snapshot
        self._run("pin 3 high\nwrite_frame 2\n", camera=camera, gpio=gpio)
        self.assertEqual(camera.pins_at_stop, [False] * 8)

    def test_pins_are_released_even_if_camera_fails(self):
        class BrokenCamera(RecordingCamera):
            def stop_recording(self, video_path: Path) -> list[str]:
                raise RuntimeError("камера отвалилась")

        gpio = StubGpio()
        with self.assertRaises(RuntimeError):
            self._run("pin 4 high\nwrite_frame 2\n", camera=BrokenCamera(), gpio=gpio)
        self.assertEqual(gpio.snapshot(), [False] * 8)

    def test_timeout_trims_the_script(self):
        result = self._run("write_frame 600\n", timeout=0)
        self.assertEqual(result.status, "error")
        self.assertIn("лимит времени", result.error_message)

    def test_timeout_also_caps_the_fallback_recording(self):
        """Сценарий без write_frame не должен пересиживать дедлайн."""
        result = self._run("pin 1 high\n", timeout=0)
        self.assertEqual(result.status, "error")
        self.assertEqual(self.camera.held, [], "нельзя снимать, когда время уже вышло")

    def test_partial_hold_when_budget_is_short(self):
        camera = RecordingCamera()
        # бюджета хватает примерно на 20 кадров при fps=10
        self._run("write_frame 600\n", camera=camera, timeout=2)
        self.assertTrue(camera.held)
        self.assertLess(camera.held[0][0], 600)


class StubCameraTests(unittest.TestCase):
    def test_live_frame_is_a_png(self):
        camera = StubCamera()
        frame = camera.live_frame([True] * 8)
        self.assertIsNotNone(frame)
        self.assertTrue(frame.startswith(b"\x89PNG"))


class GpioEngageTests(unittest.TestCase):
    """В покое линии отпущены, на время работы — захвачены целиком."""

    def test_executor_engages_before_the_script(self):
        class TrackingGpio(StubGpio):
            def __init__(self) -> None:
                super().__init__()
                self.events: list[str] = []

            def engage(self) -> None:
                self.events.append("engage")
                super().engage()

            def set_pin(self, pin: int, high: bool) -> str:
                self.events.append(f"pin{pin}")
                return super().set_pin(pin, high)

            def release(self) -> None:
                self.events.append("release")
                super().release()

        gpio = TrackingGpio()
        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            firmware = workspace / "a.svf"
            firmware.write_text("! svf\n")
            HardwareExecutor(
                programmer=FakeProgrammer(), camera=RecordingCamera(), gpio=gpio
            ).run(
                firmware_path=firmware,
                instruction_text="pin 2 high\nwrite_frame 2\n",
                workspace=workspace,
                timeout_seconds=60,
            )
        self.assertEqual(gpio.events[0], "engage", "линии надо забрать до сценария")
        self.assertEqual(gpio.events[1], "pin2")
        self.assertEqual(gpio.events[-1], "release")

    def test_engage_resets_state_to_low(self):
        gpio = StubGpio()
        gpio.set_pin(4, True)
        gpio.engage()
        self.assertEqual(gpio.snapshot(), [False] * 8)


class StubGpioTests(unittest.TestCase):
    def test_rejects_pins_outside_range(self):
        gpio = StubGpio()
        for bad in (0, 9, -1, 100):
            with self.assertRaises(ValueError):
                gpio.set_pin(bad, True)

    def test_tracks_state(self):
        gpio = StubGpio()
        gpio.set_pin(1, True)
        gpio.set_pin(8, True)
        self.assertEqual(gpio.snapshot(), [True, False, False, False, False, False, False, True])


class PinMapTests(unittest.TestCase):
    @unittest.skipUnless(SERVER_CONSTANTS.exists(), "серверная часть репозитория недоступна")
    def test_server_has_no_second_bcm_config(self):
        """BCM берётся только из конфига агента, не из серверных констант."""
        namespace: dict = {}
        source = SERVER_CONSTANTS.read_text(encoding="utf-8")
        exec(compile(source, str(SERVER_CONSTANTS), "exec"), namespace)
        self.assertEqual(len(namespace["PIN_MAP"]), 8)
        self.assertTrue(all("rpi_bcm" not in entry for entry in namespace["PIN_MAP"]))

    def test_custom_bcm_is_sent_in_heartbeat(self):
        from remote_agent.api import ServerClient
        pins = (2, 3, 4, 5, 6, 9, 10, 11)
        client = ServerClient(server_url="http://test", token="secret", gpio_pins=pins)
        with unittest.mock.patch.object(client.session, "post") as post:
            post.return_value.json.return_value = {"status": "idle"}
            client.heartbeat()
        self.assertEqual(post.call_args.kwargs["json"], {"gpio_pins": list(pins)})
        self.assertEqual(client.session.headers["Authorization"], "Token secret")

    def test_eight_unique_pins(self):
        pins = AgentConfig.from_env().gpio_pins
        self.assertEqual(len(pins), 8)
        self.assertEqual(len(set(pins)), 8)


class ProgrammerResultTests(unittest.TestCase):
    def test_missing_firmware_is_not_ok(self):
        result = RealProgrammer().program(Path("/nonexistent/none.svf"))
        self.assertFalse(result.ok)

    def test_missing_config_is_not_ok(self):
        with TemporaryDirectory() as tmp:
            firmware = Path(tmp) / "a.svf"
            firmware.write_text("! svf\n")
            result = RealProgrammer(config_path=Path(tmp) / "nope.cfg").program(firmware)
            self.assertFalse(result.ok)

    def test_frequency_line_is_commented_for_usb_blaster(self):
        import subprocess

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = root / "max10.cfg"
            cfg.write_text("# dummy\n")
            firmware = root / "a.svf"
            firmware.write_text("FREQUENCY 1.00E+07 HZ;\nSIR 10 TDI (2CC);\n")
            captured: dict[str, str] = {}

            def fake_run(command, **_kwargs):
                svf_arg = next(part for part in command if str(part).startswith("svf "))
                sent = Path(str(svf_arg).split(" ", 1)[1].split(" ", 1)[0])
                captured["svf"] = sent.read_text(encoding="utf-8")
                self.assertIn("-ignore_error", svf_arg)
                return subprocess.CompletedProcess(command, 0, "programmed successfully\n", "")

            original = firmware.read_text(encoding="utf-8")
            with unittest.mock.patch("subprocess.run", side_effect=fake_run):
                result = RealProgrammer(config_path=cfg).program(firmware)

        self.assertTrue(result.ok)
        self.assertTrue(original.startswith("FREQUENCY"))
        self.assertIn("! FREQUENCY 1.00E+07 HZ;", captured["svf"])
        self.assertIn("SIR 10 TDI (2CC);", captured["svf"])


class MjpegPipeTests(unittest.TestCase):
    """Разбор JPEG-потока: публикуем только целые кадры."""

    class FakeProcess:
        def __init__(self, chunks: list[bytes]) -> None:
            self.stdout = self._Reader(chunks)
            self.waited = 0

        def poll(self):
            return None if self.stdout.chunks else 0

        def kill(self):
            self.stdout.chunks = []

        def wait(self, timeout=None):
            self.waited += 1
            return 0

        class _Reader:
            def __init__(self, chunks: list[bytes]) -> None:
                self.chunks = list(chunks)
                self.closed = False

            def read(self, _size: int) -> bytes:
                return self.chunks.pop(0) if self.chunks else b""

            def close(self) -> None:
                self.closed = True

    def _pipe(self, chunks: list[bytes]) -> bytes | None:
        pipe = _MjpegPipe(self.FakeProcess(chunks))
        pipe._thread.join(timeout=2)
        return pipe.latest()

    def test_stop_reaps_the_process(self):
        process = self.FakeProcess([b"\xff\xd8x\xff\xd9"])
        pipe = _MjpegPipe(process)
        pipe.stop()
        self.assertEqual(process.waited, 1, "убитый ffmpeg надо дожать, иначе зомби")
        self.assertTrue(process.stdout.closed)

    def test_extracts_whole_frame(self):
        frame = b"\xff\xd8body\xff\xd9"
        self.assertEqual(self._pipe([frame]), frame)

    def test_keeps_last_complete_frame(self):
        first = b"\xff\xd8one\xff\xd9"
        second = b"\xff\xd8two\xff\xd9"
        self.assertEqual(self._pipe([first + second]), second)

    def test_ignores_partial_tail(self):
        whole = b"\xff\xd8done\xff\xd9"
        self.assertEqual(self._pipe([whole, b"\xff\xd8partial"]), whole)

    def test_handles_frame_split_across_reads(self):
        self.assertEqual(
            self._pipe([b"\xff\xd8he", b"ad", b"er\xff\xd9"]),
            b"\xff\xd8header\xff\xd9",
        )


class FakeClient:
    """Заглушка сервера: отдаёт заранее заданные ответы и пишет, что получила."""

    def __init__(self) -> None:
        self.submitted: list = []
        self.downloads: list[str] = []

    def ws_base(self) -> str:
        return "ws://test"

    def download_file(self, url: str, destination: Path) -> Path:
        self.downloads.append(url)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("! svf\n")
        return destination

    def download_firmware(self, *, job, destination: Path) -> Path:
        return self.download_file(job.download_url, destination)

    def download_instruction(self, *, job, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("pin 1 high\nwrite_frame 2\n")
        return destination

    def submit_result(self, *, job, result):
        self.submitted.append((job.id, result.status))
        return {"status": result.status}


class SessionPinConvergenceTests(unittest.TestCase):
    """Агент должен приводить пины к состоянию, которое считает верным сервер."""

    def _worker(self, gpio):
        from remote_agent.config import AgentConfig
        from remote_agent.worker import AgentWorker

        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = AgentConfig(server_url="http://test", token="t", workspace=Path(self.tmp.name))
        worker = AgentWorker(
            config=config,
            client=FakeClient(),
            executor=HardwareExecutor(programmer=FakeProgrammer(), camera=RecordingCamera(), gpio=gpio),
            gpio=gpio,
            camera=RecordingCamera(),
        )
        return worker

    def test_applies_server_state(self):
        gpio = StubGpio()
        worker = self._worker(gpio)
        worker._apply_pin_states([True, False, True, False, False, False, False, True])
        self.assertEqual(gpio.snapshot(), [True, False, True, False, False, False, False, True])

    def test_session_start_engages_lines_once(self):
        class CountingGpio(StubGpio):
            def __init__(self) -> None:
                super().__init__()
                self.engaged = 0

            def engage(self) -> None:
                self.engaged += 1
                super().engage()

        gpio = CountingGpio()
        worker = self._worker(gpio)
        session = {"pin_states": [False] * 8, "commands": []}
        with unittest.mock.patch.object(worker, "_ensure_stream"):
            worker._handle_session(session)
            worker._handle_session(session)
        self.assertEqual(gpio.engaged, 1, "на каждый опрос захватывать заново незачем")
        worker._end_session()
        with unittest.mock.patch.object(worker, "_ensure_stream"):
            worker._handle_session(session)
        self.assertEqual(gpio.engaged, 2, "новая сессия — новый захват")

    def test_converges_after_restart(self):
        """Даже если агент не видел команд, он догоняет состояние сервера."""
        gpio = StubGpio()
        worker = self._worker(gpio)
        worker._apply_pin_states([True] * 8)
        worker._apply_pin_states([False] * 8)
        self.assertEqual(gpio.snapshot(), [False] * 8)

    def test_only_touches_changed_pins(self):
        class CountingGpio(StubGpio):
            def __init__(self) -> None:
                super().__init__()
                self.writes = 0

            def set_pin(self, pin: int, high: bool) -> str:
                self.writes += 1
                return super().set_pin(pin, high)

        gpio = CountingGpio()
        worker = self._worker(gpio)
        worker._apply_pin_states([True] + [False] * 7)
        self.assertEqual(gpio.writes, 1)
        worker._apply_pin_states([True] + [False] * 7)
        self.assertEqual(gpio.writes, 1, "повторное совпадающее состояние не должно дёргать пины")

    def test_ignores_broken_pin_without_crashing(self):
        class FlakyGpio(StubGpio):
            def set_pin(self, pin: int, high: bool) -> str:
                if pin == 3:
                    raise OSError("линия занята")
                return super().set_pin(pin, high)

        gpio = FlakyGpio()
        worker = self._worker(gpio)
        worker._apply_pin_states([True] * 8)
        state = gpio.snapshot()
        self.assertFalse(state[2])
        self.assertTrue(state[0] and state[7])

    def test_session_end_releases_lines_and_camera(self):
        gpio = StubGpio()
        worker = self._worker(gpio)
        worker._in_session = True
        gpio.set_pin(5, True)
        worker._end_session()
        self.assertEqual(gpio.snapshot(), [False] * 8)
        self.assertEqual(worker.camera.closed, 1, "камеру надо отпустить, иначе ffmpeg висит")

    def test_no_session_means_nothing_to_release(self):
        gpio = StubGpio()
        worker = self._worker(gpio)
        worker._end_session()
        self.assertEqual(worker.camera.closed, 0)


class JobWorkspaceTests(unittest.TestCase):
    def test_workspace_is_cleaned_after_result_is_sent(self):
        from remote_agent.config import AgentConfig
        from remote_agent.models import RemoteJob
        from remote_agent.worker import AgentWorker

        with TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            client = FakeClient()
            camera = RecordingCamera()
            worker = AgentWorker(
                config=AgentConfig(server_url="http://test", token="t", workspace=workspace),
                client=client,
                executor=HardwareExecutor(
                    programmer=FakeProgrammer(), camera=camera, gpio=StubGpio()
                ),
                gpio=StubGpio(),
                camera=camera,
            )
            job = RemoteJob(
                id="job-1",
                status="running",
                original_filename="a.svf",
                download_url="http://test/f",
                result_url="http://test/r",
                detail_url="http://test/d",
                instruction_url="http://test/i",
                instruction_filename="a.txt",
            )
            worker._process_job(job)

            self.assertEqual(client.submitted, [("job-1", "completed")])
            self.assertFalse((workspace / "job-1").exists(), "каталог задачи должен убираться")


class LiteLangAgentTests(unittest.TestCase):
    def test_agent_and_server_reject_the_same_scripts(self):
        for bad in ("pin 9 high", "pin 0 low", "write_frame 0", "nonsense 1", ""):
            with self.assertRaises(InstructionError):
                parse_instruction(bad)

    @unittest.skipUnless(EXAMPLE_SCRIPT.exists(), "серверная часть репозитория недоступна")
    def test_accepts_the_shipped_example(self):
        commands = parse_instruction(EXAMPLE_SCRIPT.read_text(encoding="utf-8"))
        self.assertGreater(len(commands), 10)


class ConfigTests(unittest.TestCase):
    def test_hardware_config_from_env(self):
        with unittest.mock.patch.dict(
            "os.environ",
            {
                "SERVER_URL": "http://10.0.0.1:8000/",
                "AGENT_TOKEN": "tok",
                "MODE": "hardware",
                "CAMERA_DEVICE": "/dev/video2",
                "GPIO_PINS": "2,3,4,5,6,7,8,9",
            },
            clear=True,
        ):
            config = AgentConfig.from_env()
        self.assertEqual(config.server_url, "http://10.0.0.1:8000")
        self.assertEqual(config.mode, "hardware")
        self.assertEqual(config.camera_device, "/dev/video2")
        self.assertEqual(config.gpio_pins, (2, 3, 4, 5, 6, 7, 8, 9))

    def test_rejects_invalid_mode(self):
        with unittest.mock.patch.dict("os.environ", {"MODE": "wrong"}, clear=True):
            with self.assertRaises(ValueError):
                AgentConfig.from_env()


if __name__ == "__main__":
    unittest.main()
