#!/bin/bash
# install_openocd_from_source.sh – сборка OpenOCD с USB-Blaster и SVF (без libjaylink)
set -e
echo "=== Установка зависимостей для сборки OpenOCD ==="
sudo apt update
sudo apt install -y git autoconf libtool make pkg-config libusb-1.0-0-dev \
libftdi1-dev libhidapi-dev texinfo ffmpeg v4l-utils
sudo apt install -y git autoconf libtool make pkg-config libusb-1.0-0-dev \
libftdi1-dev libhidapi-dev texinfo ffmpeg
echo "=== Клонирование репозитория OpenOCD ==="
cd /tmp
if [ -d openocd ]; then
rm -rf openocd
fi
git clone https://git.code.sf.net/p/openocd/code openocd
cd openocd
# === Инициализация подмодуля jimtcl (но не libjaylink) ===
echo "=== Инициализация подмодуля jimtcl (без libjaylink) ==="
# Инициализируем только нужные подмодули, libjaylink пропускаем
git submodule update --init --recursive -- \
    $(git config --file .gitmodules --get-regexp path | grep -v libjaylink | cut -d' ' -f2)
echo "=== Генерация конфигурационных файлов (bootstrap) ==="
./bootstrap
echo "=== Конфигурация с поддержкой USB-Blaster, SVF, внутренним jimtcl и без libjaylink ==="
# --disable-internal-libjaylink пропускает скачивание/сборку libjaylink (не нужен для USB-Blaster)
./configure --enable-usb-blaster --enable-svf --enable-ftdi --enable-maintainer-mode \
--enable-internal-jimtcl --disable-internal-libjaylink
echo "=== Компиляция (может занять несколько минут) ==="
make -j$(nproc)
echo "=== Установка собранного OpenOCD ==="
sudo make install
sudo ldconfig
echo "=== Проверка версии и поддержки USB-Blaster ==="
openocd --version
echo "Проверка драйвера usb_blaster:"
openocd -c "interface usb_blaster; exit" 2>&1 | head -5
echo "=== Настройка правил udev для USB-Blaster ==="
UDEV_RULE_FILE="/etc/udev/rules.d/51-usb-blaster.rules"
if [ ! -f "$UDEV_RULE_FILE" ]; then
sudo bash -c 'cat > /etc/udev/rules.d/51-usb-blaster.rules' <<EOF
SUBSYSTEM=="usb", ATTR{idVendor}=="09fb", ATTR{idProduct}=="6001", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="09fb", ATTR{idProduct}=="6002", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="09fb", ATTR{idProduct}=="6003", MODE="0666"
SUBSYSTEM=="usb", ATTR{idVendor}=="09fb", ATTR{idProduct}=="6010", MODE="0666"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "Правила добавлены."
else
echo "Правила уже существуют."
fi
echo "=== Проверка ffmpeg ==="
ffmpeg -version | head -1
echo "=== Установка завершена. Перезагрузите систему или переподключите USB-Blaster. ==="