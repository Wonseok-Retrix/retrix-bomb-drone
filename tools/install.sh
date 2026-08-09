#!/usr/bin/env bash
# Raspberry Pi Zero W / Zero 2 W 에서 한 번만 실행하는 설치 스크립트.
#   bash tools/install.sh
set -e

CONFIG=/boot/firmware/config.txt
[ -f "$CONFIG" ] || CONFIG=/boot/config.txt   # 구버전 OS 호환

add_config() {   # 중복 없이 config.txt 에 한 줄 추가
  grep -qxF "$1" "$CONFIG" || echo "$1" | sudo tee -a "$CONFIG" > /dev/null
}

echo "== 1/5 시스템 업데이트 =="
sudo apt update && sudo apt full-upgrade -y

echo "== 2/5 IMX500 AI 카메라 =="
# imx500-all = 카메라 펌웨어 + 기본 모델(/usr/share/imx500-models) + .rpk 포장 도구
# OpenCV 는 설치하지 않습니다. picamera2 는 pillow + simplejpeg 만 사용합니다.
sudo apt install -y imx500-all python3-picamera2 python3-simplejpeg python3-pil

echo "== 3/5 파이썬 패키지 =="
# Bookworm 은 시스템 파이썬을 보호합니다(PEP 668).
# apt 로 설치한 picamera2 를 그대로 쓰기 위해 venv 를 만들지 않습니다.
sudo apt install -y python3-yaml
# gpiozero + lgpio = 서보 드로퍼를 GPIO 로 직접 제어하는 데 사용합니다
sudo apt install -y python3-gpiozero python3-lgpio
# pymavlink 는 apt 패키지를 우선 사용합니다.
# (Raspberry Pi OS Lite 에는 pip3 가 기본 설치되어 있지 않습니다)
if ! sudo apt install -y python3-pymavlink; then
  echo "-- apt 에 python3-pymavlink 가 없어 pip 로 설치합니다 --"
  sudo apt install -y python3-pip
  pip3 install --break-system-packages pymavlink
fi

echo "== 4/5 시리얼 포트 (비행 컨트롤러 연결) =="
# Zero W / Zero 2 W 는 블루투스가 PL011(ttyAMA0)을 쓰고 있어서,
# 그냥 두면 GPIO 14/15 에는 mini UART(ttyS0)가 붙습니다.
# mini UART 는 자체 클럭이 없어 보드레이트가 CPU 클럭에 따라 흔들립니다.
# -> 블루투스를 꺼서 PL011 을 GPIO 로 되돌립니다. (/dev/serial0 -> ttyAMA0)
add_config "enable_uart=1"
add_config "dtoverlay=disable-bt"
sudo systemctl disable hciuart 2>/dev/null || true

sudo raspi-config nonint do_serial_hw 0     # 하드웨어 UART 켜기
sudo raspi-config nonint do_serial_cons 1   # 시리얼 로그인 콘솔 끄기
sudo usermod -aG dialout "$USER"

echo "== 5/5 헤드리스 설정 =="
# 화면 출력을 쓰지 않으므로 GPU 메모리를 최소로 (Zero W 의 512MB 확보)
add_config "gpu_mem=64"

echo
echo "설치 완료. 재부팅하세요:  sudo reboot"
echo "재부팅 후 순서:"
echo "  1) python3 tools/check_camera.py"
echo "  2) python3 tools/check_mavlink.py"
