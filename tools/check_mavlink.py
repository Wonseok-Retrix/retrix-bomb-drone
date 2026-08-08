#!/usr/bin/env python3
"""2단계 점검: Pi <-> 비행 컨트롤러 MAVLink 연결 확인.

    python3 tools/check_mavlink.py

하트비트, 비행 모드, 시동 상태, 배터리, GPS 를 계속 출력합니다.
프로펠러를 뺀 상태에서 실행하세요.
"""

import os
import sys
import time

import yaml
from pymavlink import mavutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    with open(os.path.join(ROOT, "config.yaml")) as f:
        m = yaml.safe_load(f)["mavlink"]

    print(f"연결 중: {m['connection']} @ {m['baud']}")
    master = mavutil.mavlink_connection(m["connection"], baud=m["baud"])

    print("하트비트 대기중... (안 오면 배선/보드레이트/SERIALx_PROTOCOL 확인)")
    master.wait_heartbeat()
    print(f"OK! system={master.target_system} component={master.target_component}\n")

    # 필요한 데이터를 4Hz 로 보내달라고 요청
    master.mav.request_data_stream_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1,
    )

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
                state["mode"] = mavutil.mode_string_v10(msg)
                state["armed"] = bool(
                    msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
                )
            elif t == "SYS_STATUS":
                state["batt"] = msg.voltage_battery / 1000.0
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
