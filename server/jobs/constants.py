from __future__ import annotations

HEARTBEAT_TTL_SECONDS = 15
SESSION_DURATION_SECONDS = 15 * 60
PIN_COUNT = 8

# Логический пин 1..8 → BCM Raspberry Pi и GPIO_[n] на DE10-Lite JP1
# (GPIO_19 = контакт 22, не путать с номером штыря: JP1 pin 29 = 3.3V).
PIN_MAP = [
    {"index": 1, "rpi_bcm": 21, "de10_gpio": 19, "fpga": "PIN_W11"},
    {"index": 2, "rpi_bcm": 20, "de10_gpio": 21, "fpga": "PIN_AA10"},
    {"index": 3, "rpi_bcm": 16, "de10_gpio": 23, "fpga": "PIN_Y8"},
    {"index": 4, "rpi_bcm": 12, "de10_gpio": 25, "fpga": "PIN_Y7"},
    {"index": 5, "rpi_bcm": 1, "de10_gpio": 27, "fpga": "PIN_Y6"},
    {"index": 6, "rpi_bcm": 7, "de10_gpio": 29, "fpga": "PIN_Y5"},
    {"index": 7, "rpi_bcm": 8, "de10_gpio": 31, "fpga": "PIN_Y4"},
    {"index": 8, "rpi_bcm": 25, "de10_gpio": 33, "fpga": "PIN_Y3"},
]
