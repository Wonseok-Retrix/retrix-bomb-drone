#!/usr/bin/env python3
"""2단계 점검: Pi <-> 비행 컨트롤러(ArduCopter) MAVLink 연결 확인.

    python3 tools/check_mavlink.py

하트비트, 비행 모드, 시동 상태, 배터리, GPS 를 계속 출력합니다.
프로펠러를 뺀 상태에서 실행하세요.

이 도구는 상태만 읽으며 시동, 모드 전환, 속도 명령을 수행하지 않습니다.
"""

import os
import sys
import time

import yaml
from pymavlink import mavutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from mavlink_link import arducopter_mode_string

# 이 점검 화면에 필요한 메시지들을 MAV_CMD_SET_MESSAGE_INTERVAL 로 요청합니다.
WANTED = [
    mavutil.mavlink.MAVLINK_MSG_ID_SYS_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS,
    mavutil.mavlink.MAVLINK_MSG_ID_GPS_RAW_INT,
    mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
]

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

    print(f"Connecting: {m['connection']} @ {m['baud']}")
    master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])

    print("Waiting for heartbeat... (check wiring, baud rate, and SERIALx_PROTOCOL if none arrives)")
    master.wait_heartbeat()
    print(f"OK! system={master.target_system} component={master.target_component}\n")

    request_messages(master)

    state = {}
    last = 0.0
    try:
        while True:
            msg = master.recv_match(blocking=True, timeout=2)
            if msg is None:
                print("... no messages")
                continue
            t = msg.get_type()

            if t == "HEARTBEAT":
                if msg.get_srcSystem() != master.target_system:
                    continue          # 지상국 등 다른 기기의 하트비트는 무시
                state["mode"] = arducopter_mode_string(msg)
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
        print("\nStopped")


if __name__ == "__main__":
    main()
