#!/usr/bin/env bash
# 부팅 자동 실행 systemd 서비스를 중지하고 제거합니다.
# 저장소 안에서 실행하세요: bash tools/uninstall_autostart.sh
set -euo pipefail

SERVICE_NAME="retrix-bomb-drone.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"

echo "Stopping and disabling service: ${SERVICE_NAME}"
sudo systemctl disable --now "${SERVICE_NAME}" 2>/dev/null || true

if [[ -f "${SERVICE_FILE}" ]]; then
  sudo rm -f -- "${SERVICE_FILE}"
fi

sudo systemctl daemon-reload
sudo systemctl reset-failed "${SERVICE_NAME}" 2>/dev/null || true

echo "Removed: ${SERVICE_FILE}"
echo "To install again: bash tools/install_autostart.sh"
