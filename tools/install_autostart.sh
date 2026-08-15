#!/usr/bin/env bash
# 부팅 시 추적 프로그램을 LIVE 모드로 자동 실행하는 systemd 서비스 등록.
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
  echo "오류: root가 아닌 실제 비행용 계정으로 실행하세요."
  echo "예: bash tools/install_autostart.sh"
  exit 1
fi

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "오류: ${PYTHON_BIN}을 찾을 수 없습니다."
  exit 1
fi

if [[ ! -f "${MAIN_SCRIPT}" ]]; then
  echo "오류: ${MAIN_SCRIPT}을 찾을 수 없습니다."
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
  "ExecStart=${PYTHON_BIN} ${MAIN_SCRIPT} --live" \
  'Restart=always' \
  'RestartSec=5' \
  'KillSignal=SIGINT' \
  'TimeoutStopSec=5' \
  'Environment=PYTHONUNBUFFERED=1' \
  '' \
  '[Install]' \
  'WantedBy=multi-user.target' \
  > "${TEMP_SERVICE}"

echo "서비스를 등록합니다: ${SERVICE_NAME}"
echo "실행 계정: ${RUN_USER}"
echo "프로젝트: ${PROJECT_DIR}"

sudo install -o root -g root -m 0644 "${TEMP_SERVICE}" "${SERVICE_FILE}"
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}"

echo
echo "등록 완료: 부팅 시 LIVE 모드로 자동 실행됩니다."
echo "상태 확인: systemctl status ${SERVICE_NAME}"
echo "로그 확인: journalctl -u ${SERVICE_NAME} -f"
echo "자동 실행 해제: bash tools/uninstall_autostart.sh"
