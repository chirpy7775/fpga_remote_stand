from __future__ import annotations

PIN_COUNT = 8

# Логический пин 1..8 → GPIO_[n] на DE10-Lite JP1.
# BCM сообщает каждый агент из своего GPIO_PINS, здесь второй копии нет.
# (GPIO_19 = контакт 22, не путать с номером штыря: JP1 pin 29 = 3.3V).
PIN_MAP = [
    {"index": 1, "de10_gpio": 19, "fpga": "PIN_W11"},
    {"index": 2, "de10_gpio": 21, "fpga": "PIN_AA10"},
    {"index": 3, "de10_gpio": 23, "fpga": "PIN_Y8"},
    {"index": 4, "de10_gpio": 25, "fpga": "PIN_Y7"},
    {"index": 5, "de10_gpio": 27, "fpga": "PIN_Y6"},
    {"index": 6, "de10_gpio": 29, "fpga": "PIN_Y5"},
    {"index": 7, "de10_gpio": 31, "fpga": "PIN_Y4"},
    {"index": 8, "de10_gpio": 33, "fpga": "PIN_Y3"},
]
