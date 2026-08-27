from __future__ import annotations

import struct
import zlib

WIDTH = 320
HEIGHT = 240


def _chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def rgb_to_png(pixels: bytes, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    raw = bytearray()
    row_size = width * 3
    for y in range(height):
        raw.append(0)
        start = y * row_size
        raw.extend(pixels[start : start + row_size])
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )


def render_stub_frame(pins: list[bool], tick: int, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    pixels = bytearray(width * height * 3)
    bg = (28, 16, 48)
    for i in range(0, len(pixels), 3):
        pixels[i] = bg[0]
        pixels[i + 1] = bg[1]
        pixels[i + 2] = bg[2]

    stripe_x = tick % width
    for y in range(height):
        idx = (y * width + stripe_x) * 3
        pixels[idx] = 140
        pixels[idx + 1] = 90
        pixels[idx + 2] = 220

    bar_w = max(width // 8, 8)
    bar_top = height - 42
    for i in range(8):
        on = bool(i < len(pins) and pins[i])
        color = (52, 211, 153) if on else (55, 48, 74)
        x0 = i * bar_w + 4
        x1 = min((i + 1) * bar_w - 4, width)
        for y in range(bar_top, height - 6):
            for x in range(x0, x1):
                idx = (y * width + x) * 3
                pixels[idx] = color[0]
                pixels[idx + 1] = color[1]
                pixels[idx + 2] = color[2]
    return rgb_to_png(bytes(pixels), width, height)
