#!/usr/bin/env bash
# 부팅 시 추적 프로그램을 자동 실행하는 systemd 서비스 등록.
# 저장소 안에서 실행하세요: bash tools/install_autostart.sh
set -euo pipefail

SERVICE_NAME="retrix-bomb-drone.service"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
RUN_USER="${SUDO_USER:-$(id -un)}"
PYTHON_BIN="/usr/bin/python3"
MAIN_SCRIPT="${PROJECT_DIR}/src/track_and_follow.py"
TEMP_SERVICE="$(mktemp)"

cleanup() {
  rm -f -- "${TEMP_SERVICE}"
}
trap cleanup EXIT

if [[ "${RUN_USER}" == "root" ]]; then
  echo "Error: run this as the non-root flight account."
  echo "Example: bash tools/install_autostart.sh"
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Error: ${PYTHON_BIN} was not found."
  exit 1
fi

if [[ ! -f "${MAIN_SCRIPT}" ]]; then
  echo "Error: ${MAIN_SCRIPT} was not found."
  exit 1
fi

printf '%s\n' \
  '[Unit]' \
  'Description=Retrix Bomb Drone OBC' \
  'After=multi-user.target' \
  'Wants=multi-user.target' \
  '' \
  '[Service]' \
  'Type=simple' \
  "User=${RUN_USER}" \
  'SupplementaryGroups=dialout gpio video' \
  "WorkingDirectory=${PROJECT_DIR}" \
  "ExecStart=${PYTHON_BIN} ${MAIN_SCRIPT}" \
  'Restart=always' \
  'RestartSec=5' \
  'KillSignal=SIGINT' \
  'TimeoutStopSec=5' \
  'Environment=PYTHONUNBUFFERED=1' \
  '' \
  '[Install]' \
  'WantedBy=multi-user.target' \
  > "${TEMP_SERVICE}"

echo "Installing service: ${SERVICE_NAME}"
echo "Run user: ${RUN_USER}"
echo "Project: ${PROJECT_DIR}"

sudo install -o root -g root -m 0644 "${TEMP_SERVICE}" "${SERVICE_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo
echo "Installed: tracking will start automatically at boot."
echo "Check status: systemctl status ${SERVICE_NAME}"
echo "View logs: journalctl -u ${SERVICE_NAME} -f"
echo "Disable autostart: bash tools/uninstall_autostart.sh"
