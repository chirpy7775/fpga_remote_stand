# GPIO test, Terasic DE10-Lite (чип 10M50DAF484C7G)

Пины сверены с User Manual (GPIO JP1, LEDR) и официальным `DE10_Lite.qsf`.
Линии с малины — **только входы**, FPGA их не драйвит. 3.3 V LVTTL, как на разъёме JP1.

## Что видно на плате

| LED | Смысл |
|---|---|
| LEDR0…LEDR7 | Пины стенда 1…8 (high → горит) |
| LEDR8 | Все 8 high |
| LEDR9 | Мигает само (~0.75 Гц) — битстрим живой |

## Распиновка

`de10_gpio` в коде стенда — это **GPIO_[n]**, не номер контакта на гребенке. Контакт **29 на JP1 = 3.3 V**, его малине не сажать.

| GPIO | BCM Pi по умолчанию | GPIO_[n] | Контакт JP1 | FPGA |
|---|---|---|---|---|
| 1 | 21 | 19 | 22 | `PIN_W11` |
| 2 | 20 | 21 | 24 | `PIN_AA10` |
| 3 | 16 | 23 | 26 | `PIN_Y8` |
| 4 | 12 | 25 | 28 | `PIN_Y7` |
| 5 | 1 | 27 | 32 | `PIN_Y6` |
| 6 | 7 | 29 | 34 | `PIN_Y5` |
| 7 | 8 | 31 | 36 | `PIN_Y4` |
| 8 | 25 | 33 | 38 | `PIN_Y3` |

Не подключать JP1 pin 11 (5 V). Общий GND — pin 12 или 30.

## Сборка в Quartus 17

1. File → Open Project → `gpio_led_test.qpf`
2. Processing → Start Compilation
3. SVF:

```text
quartus_cpf -c --operation=BP --voltage=3.3 --freq=10MHz output_files\gpio_led_test.sof gpio_led_test.svf
```

После заливки LEDR9 мигает без Pi. Дальше пины 1–8 в UI → LEDR0–7. Если
включить все восемь, загорится ещё LEDR8. Сценарий: `gpio_test.txt`.

BCM в таблице соответствуют стандартному `GPIO_PINS` из `agent/.env`. Если
на агенте указана другая распиновка, подключать нужно по его фактическому
`GPIO_PINS`; веб-интерфейс показывает переданное агентом значение.
