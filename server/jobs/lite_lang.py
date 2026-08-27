from __future__ import annotations

from dataclasses import dataclass


ALLOWED_PINS = frozenset(range(1, 9))
MAX_TOTAL_FRAMES = 600


class InstructionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PinCommand:
    pin: int
    state: str


@dataclass(frozen=True, slots=True)
class WriteFrameCommand:
    frames: int


InstructionCommand = PinCommand | WriteFrameCommand


def parse_instruction(
    text: str,
    *,
    allowed_pins: frozenset[int] = ALLOWED_PINS,
) -> list[InstructionCommand]:
    commands: list[InstructionCommand] = []
    total_frames = 0

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        verb = parts[0].lower()

        if verb == "pin":
            if len(parts) != 3:
                raise InstructionError(f"Строка {line_no}: ожидается `pin <номер> <high|low>`.")
            try:
                pin = int(parts[1])
            except ValueError as exc:
                raise InstructionError(f"Строка {line_no}: номер пина должен быть числом.") from exc
            state = parts[2].lower()
            if state not in {"high", "low"}:
                raise InstructionError(f"Строка {line_no}: состояние пина только high или low.")
            if pin not in allowed_pins:
                raise InstructionError(
                    f"Строка {line_no}: пин {pin} не разрешён. Допустимы {sorted(allowed_pins)}."
                )
            commands.append(PinCommand(pin=pin, state=state))
            continue

        if verb == "write_frame":
            if len(parts) != 2:
                raise InstructionError(f"Строка {line_no}: ожидается `write_frame <кадры>`.")
            try:
                frames = int(parts[1])
            except ValueError as exc:
                raise InstructionError(f"Строка {line_no}: количество кадров должно быть числом.") from exc
            if frames <= 0:
                raise InstructionError(f"Строка {line_no}: write_frame принимает положительное число.")
            total_frames += frames
            if total_frames > MAX_TOTAL_FRAMES:
                raise InstructionError(
                    f"Слишком длинный сценарий: больше {MAX_TOTAL_FRAMES} кадров."
                )
            commands.append(WriteFrameCommand(frames=frames))
            continue

        raise InstructionError(f"Строка {line_no}: неизвестная команда `{parts[0]}`.")

    if not commands:
        raise InstructionError("Файл инструкции пуст.")
    return commands
