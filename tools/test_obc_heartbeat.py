#!/usr/bin/env python3
"""OBC -> FC -> GCS MAVLink 라우팅 점검.

기존 비행 프로그램을 중지한 뒤 실행합니다.

    sudo systemctl stop retrix-bomb-drone.service
    python3 tools/test_obc_heartbeat.py

다음 메시지를 OBC(SYSID 255 / COMPID 191)에서 전송합니다.

* HEARTBEAT: 1 Hz, type=18 (ONBOARD_CONTROLLER)
* NAMED_VALUE_INT: 1 Hz, OBC_COUNT 증가값
* STATUSTEXT: 5초마다 "OBC DEBUG alive ..."

Mission Planner의 MAVLink Inspector와 Messages 화면에서 확인할 수 있습니다.
이 도구는 시동, 모드 변경 또는 이동 명령을 전송하지 않습니다.
"""

import argparse
import os
import time

import yaml
from pymavlink import mavutil


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG = os.path.join(ROOT, "config.yaml")


def parse_args():
    parser = argparse.ArgumentParser(description="Test OBC MAVLink transmission and routing")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument(
        "--system-id",
        type=int,
        default=255,
        help="GCS SYSID used by the OBC (default: 255)",
    )
    parser.add_argument(
        "--component-id",
        type=int,
        default=191,
        help="OBC COMPID (default: 191, MAV_COMP_ID_ONBOARD_COMPUTER)",
    )
    parser.add_argument(
        "--text-interval",
        type=float,
        default=5.0,
        help="STATUSTEXT interval in seconds (default: 5)",
    )
    return parser.parse_args()


def load_connection(path):
    with open(path, encoding="utf-8") as f:
        mavlink = yaml.safe_load(f)["mavlink"]
    return mavlink["connection"], mavlink["baud"]


def send_heartbeat(master):
    master.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
        mavutil.mavlink.MAV_AUTOPILOT_INVALID,
        0,
        0,
        mavutil.mavlink.MAV_STATE_ACTIVE,
    )


def send_debug_value(master, started_at, count):
    elapsed_ms = int((time.monotonic() - started_at) * 1000) & 0xFFFFFFFF
    master.mav.named_value_int_send(elapsed_ms, b"OBC_COUNT", count)


def send_status_text(master, count):
    text = f"OBC DEBUG alive count={count}"
    master.mav.statustext_send(
        mavutil.mavlink.MAV_SEVERITY_INFO,
        text.encode("ascii"),
    )


def main():
    args = parse_args()
    connection, baud = load_connection(args.config)

    print(f"Connecting: {connection} @ {baud}")
    master = mavutil.mavlink_connection(
        connection,
        baud=baud,
        source_system=args.system_id,
        source_component=args.component_id,
    )

    print("Waiting for FC HEARTBEAT...")
    fc_heartbeat = master.wait_heartbeat()
    print(
        "FC received: "
        f"SYSID={fc_heartbeat.get_srcSystem()} "
        f"COMPID={fc_heartbeat.get_srcComponent()} "
        f"type={fc_heartbeat.type} autopilot={fc_heartbeat.autopilot}"
    )
    print(
        f"Starting OBC transmission: SYSID={args.system_id} COMPID={args.component_id}\n"
        "  HEARTBEAT type=18     : 1 Hz\n"
        "  NAMED_VALUE_INT       : OBC_COUNT, 1 Hz\n"
        f"  STATUSTEXT            : every {args.text_interval:g} s\n"
        "Exit: Ctrl+C"
    )

    started_at = time.monotonic()
    next_heartbeat = 0.0
    next_text = 0.0
    count = 0

    try:
        while True:
            now = time.monotonic()

            if now >= next_heartbeat:
                count += 1
                send_heartbeat(master)
                send_debug_value(master, started_at, count)
                print(f"TX OBC HEARTBEAT type=18, OBC_COUNT={count}")
                next_heartbeat = now + 1.0

            if now >= next_text:
                send_status_text(master, count)
                print(f"TX STATUSTEXT: OBC DEBUG alive count={count}")
                next_text = now + args.text_interval

            # 수신 버퍼도 비워 UART 양방향 통신이 유지되는지 확인합니다.
            while master.recv_match(blocking=False) is not None:
                pass

            time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        master.close()


if __name__ == "__main__":
    main()
