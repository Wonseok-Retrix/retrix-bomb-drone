#!/usr/bin/env python3
"""2단계 점검: Pi <-> 비행 컨트롤러(PX4) MAVLink 연결 확인.

    python3 tools/check_mavlink.py

하트비트, 비행 모드, 시동 상태, 배터리, GPS 를 계속 출력합니다.
프로펠러를 뺀 상태에서 실행하세요.

모드가 OFFBOARD 로 뜨는지까지 확인하려면 src/track_and_follow.py --live 가
따로 돌고 있어야 합니다. PX4 는 setpoint 가 흐르지 않으면 OFFBOARD 진입을
거부하는데, 이 스크립트는 setpoint 를 보내지 않기 때문입니다.
"""

import os
import sys
import time

import yaml
from pymavlink import mavutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 이 점검 화면에 필요한 메시지들. PX4 는 ArduPilot 의 REQUEST_DATA_STREAM 을
# 무시하므로 MAV_CMD_SET_MESSAGE_INTERVAL 로 하나씩 요청합니다.
WANTED = [
    mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
]

PX4_MAIN_MODE = {
    1: "MANUAL", 2: "ALTCTL", 3: "POSCTL", 4: "AUTO", 5: "ACRO",
    6: "OFFBOARD", 7: "STABILIZED", 8: "RATTITUDE", 9: "SIMPLE",
    10: "TERMINATION",
}


def px4_mode_string(msg):
    """PX4 HEARTBEAT -> 모드 이름 (custom_mode 상위 바이트가 main mode)."""
    if not msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED:
        return "MANUAL"
    main_mode = (msg.custom_mode >> 16) & 0xFF
    return PX4_MAIN_MODE.get(main_mode, f"MODE({main_mode})")


def request_messages(master, hz=4):
    interval_us = int(1_000_000 / hz)
    for msg_id in WANTED:
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            msg_id, interval_us, 0, 0, 0, 0, 0,
        )


def main():
    with open(os.path.join(ROOT, "config.yaml")) as f:
        m = yaml.safe_load(f)["mavlink"]

    print(f"연결 중: {m['connection']} @ {m['baud']}")
    master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])

    print("하트비트 대기중... (안 오면 배선/보드레이트/MAV_x_CONFIG 확인)")
    master.wait_heartbeat()
    print(f"OK! system={master.target_system} component={master.target_component}\n")

    request_messages(master)

    state = {}
    last = 0.0
    try:
        while True:
            msg = master.recv_match(blocking=True, timeout=2)
            if msg is None:
                print("... 메시지 없음")
                continue
            t = msg.get_type()

            if t == "HEARTBEAT":
                if msg.get_srcSystem() != master.target_system:
                    continue          # 지상국 등 다른 기기의 하트비트는 무시
                state["mode"] = px4_mode_string(msg)
                state["armed"] = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
            elif t == "SYS_STATUS":
                state["batt"] = msg.voltage_battery / 1000.0
            elif t == "BATTERY_STATUS":
                if msg.voltages and msg.voltages[0] != 65535:
                    state["batt"] = msg.voltages[0] / 1000.0
            elif t == "GPS_RAW_INT":
                state["fix"] = msg.fix_type
                state["sats"] = msg.satellites_visible
            elif t == "ATTITUDE":
                state["yaw"] = msg.yaw * 57.2958
            elif t == "STATUSTEXT":
                print(f"  [FC] {msg.text}")

            now = time.monotonic()
            if now - last > 1.0:
                print(
                    f"mode={state.get('mode','?'):10s} "
                    f"armed={state.get('armed','?')!s:5s} "
                    f"batt={state.get('batt',0):.1f}V "
                    f"gps fix={state.get('fix','?')} sats={state.get('sats','?')} "
                    f"yaw={state.get('yaw',0):+.0f}deg"
                )
                last = now
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
