#!/usr/bin/env python3
"""PX4 모터 개별 회전 테스트 (MAV_CMD_DO_MOTOR_TEST).

    python3 tools/motor_mov.py <motor> <speed>

    motor : 0 ~ 3      (모터 번호, 0-based)
    speed : 0 ~ 100    (회전 속도 %)

예시:
    python3 tools/motor_mov.py 1 20     # 모터 1번 20% 속도로 회전
    python3 tools/motor_mov.py 3 100    # 모터 3번 최대 속도
    python3 tools/motor_mov.py 0 0      # 모터 0번 정지

[!] 반드시 프로펠러를 제거한 상태에서 실행하세요. PX4 모터 테스트는
    시동(arm) 없이도 실제 모터를 회전시킵니다.

FC 에서 수신되는 모든 MAVLink 메시지를 실시간으로 출력합니다.
Ctrl+C 로 종료하면 모든 모터에 정지 명령을 보냅니다.
"""

import os
import sys
import threading
import time

import yaml
from pymavlink import mavutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 수신 화면에 필요한 메시지들. PX4 는 ArduPilot 의 REQUEST_DATA_STREAM 을
# 무시하므로 MAV_CMD_SET_MESSAGE_INTERVAL 로 하나씩 요청합니다.
WANTED = [
    mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
]


def usage():
    print(__doc__)
    sys.exit(1)


def request_messages(master, hz=4):
    """주요 상태 메시지를 FC 에 요청 (check_mavlink.py 와 동일 방식)."""
    interval_us = int(1_000_000 / hz)
    for msg_id in WANTED:
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            msg_id, interval_us, 0, 0, 0, 0, 0,
        )


def send_motor_stop(master, motor):
    """특정 모터에 정지 명령 (throttle=0, duration=0)."""
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
        motor,
        0,          # param2: MAV_MOTOR_TEST_THROTTLE_PERCENT (스로틀 % 단위)
        0,          # throttle 0%
        0,          # duration 0 -> 즉시 정지
        1,          # 모터 1개만
        0, 0,
    )


def send_motor_run(master, motor, speed):
    """선택한 모터를 speed(%) 로 회전 (무한 지속, 종료 시 정지 명령으로 중단)."""
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_MOTOR_TEST, 0,
        motor,
        0,          # param2: MAV_MOTOR_TEST_THROTTLE_PERCENT (스로틀 % 단위)
        float(speed),
        -1,         # 무한 지속
        1,          # 모터 1개만
        0, 0,
    )


def stop_all_motors(master):
    """모든 모터(0~3)에 정지 명령을 보내고 잠시 뒤 재전송(패킷 유실 대비)."""
    for _ in range(2):
        for m in range(4):
            send_motor_stop(master, m)
        time.sleep(0.2)


def rx_loop(master):
    """수신 스레드: 도착하는 모든 MAVLink 메시지를 실시간 출력."""
    try:
        while True:
            msg = master.recv_match(blocking=True, timeout=1)
            if msg is None:
                continue
            line = msg.get_type()
            try:
                # STATUSTEXT 는 FC 가 보낸 텍스트이므로 내용까지 표시
                if line == "STATUSTEXT":
                    line += f"  [FC] {msg.text}"
                # HEARTBEAT 는 mode/armed 상태 표시
                elif line == "HEARTBEAT":
                    if msg.get_srcSystem() == master.target_system:
                        armed = bool(
                            msg.base_mode
                            & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                        )
                        line += f"  armed={armed!s:5s}"
                # ATTITUDE 는 yaw 정도만 간단히
                elif line == "ATTITUDE":
                    line += f"  yaw={msg.yaw * 57.2958:+.0f}deg"
            except Exception:
                pass
            print(f"[RX] {line}")
    except Exception as e:
        print(f"[RX 스레드 종료] {e}")


def main():
    if len(sys.argv) != 3:
        usage()

    try:
        motor = int(sys.argv[1])
        speed = int(sys.argv[2])
    except ValueError:
        usage()

    if not (0 <= motor <= 3):
        print(f"모터 번호는 0~3 사이여야 합니다. (입력: {motor})")
        usage()
    if not (0 <= speed <= 100):
        print(f"속도는 0~100 사이여야 합니다. (입력: {speed})")
        usage()

    # ---- 안전 경고 배너 ----
    print("=" * 60)
    print("  [!] 모터 개별 회전 테스트")
    print("  [!] 프로펠러가 완전히 제거되었는지 확인하세요!")
    print("  [!] 모터 테스트는 시동(arm) 없이 실제로 회전합니다.")
    print("=" * 60)
    if speed > 0:
        print(f"\n모터 {motor}번을 {speed}% 속도로 회전시킵니다.")
        print("5초 후 시작합니다... (Ctrl+C 로 취소)\n")
        try:
            time.sleep(5)
        except KeyboardInterrupt:
            print("\n취소됨. 종료합니다.")
            return
    else:
        print(f"\n모터 {motor}번 정지 모드로 실행합니다.\n")

    # ---- MAVLink 연결 ----
    with open(os.path.join(ROOT, "config.yaml")) as f:
        m = yaml.safe_load(f)["mavlink"]

    print(f"연결 중: {m['connection']} @ {m['baud']}")
    master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])

    print("하트비트 대기중...")
    master.wait_heartbeat()
    print(f"OK! system={master.target_system} component={master.target_component}")

    # 상태 메시지 요청 (HEARTBEAT 는 항상 오므로 제외)
    request_messages(master)
    print("상태 메시지 요청 완료 (SYS_STATUS, BATTERY_STATUS, GPS, ATTITUDE @4Hz)\n")

    # ---- 수신 스레드 시작 ----
    t = threading.Thread(target=rx_loop, args=(master,), daemon=True)
    t.start()

    try:
        if speed == 0:
            print("정지 명령 전송: 모터 0~3 throttle=0")
            stop_all_motors(master)
            print("모든 모터가 정지 상태입니다. (메시지 수신 중, Ctrl+C 로 종료)")
        else:
            print(f"명령 시작: 모터 {motor}번 @ {speed}% (1Hz 재전송)")
            print("Ctrl+C 로 종료하면 모든 모터가 정지합니다.\n")

        # 1Hz 로 명령 재전송 (모터 테스트 세션 유지)
        while True:
            if speed > 0:
                send_motor_run(master, motor, speed)
            time.sleep(1.0)

    except KeyboardInterrupt:
        print("\n\n종료 명령: 모든 모터 정지...")
        stop_all_motors(master)
        print("모든 모터가 정지되었습니다. 종료합니다.")


if __name__ == "__main__":
    main()