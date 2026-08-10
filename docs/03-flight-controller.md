# 03. 비행 컨트롤러 설정 (MicoAir 743 v2 / PX4)

비행 컨트롤러(FC)와 QGroundControl(GCS)을 연결하고, MAVLink 통신 및 자율비행(OFFBOARD) 관련 파라미터를 설정하는 절차입니다.

---

## 1. 펌웨어 및 GCS 설치

| 항목 | 선택 / 설정 값 | 비고 |
| :--- | :--- | :--- |
| **GCS 소프트웨어** | **QGroundControl** (최신 안정 버전) | [공식 다운로드 링크](https://qgroundcontrol.com/) |
| **FC 펌웨어** | **PX4 Autopilot** (MicoAir H743 타겟) | QGroundControl → Vehicle Setup → Firmware |
| **기체 프레임** | **Quadrotor X** | Airframe 메뉴에서 사각 멀티콥터 X 폼팩터 선택 |

---

## 2. 필수 센서 및 기체 캘리브레이션

> [!IMPORTANT]
> 아래 5가지 캘리브레이션을 순서대로 완전히 마쳐야 PX4에서 OFFBOARD 모드 진입이 승인됩니다. 하나라도 누락되면 모드 전환이 거부됩니다.

1. **Sensor Calibration** (가속도계 6면, 자이로, 지자기/나침반)
2. **Level Horizon Calibration** (수평 캘리브레이션)
3. **Radio Calibration** (조종기 채널 및 스틱 범위)
4. **ESC Calibration** (변속기 신호 범위)
5. **Power Setup** (배터리 셀 수 및 전압 센서)

---

## 3. 시리얼 포트 설정 (TELEM2 ↔ Pi MAVLink)

MicoAir 743 v2의 **TELEM2 포트**를 라즈베리파이 컴패니언 컴퓨터 통신 전용 포트로 배정합니다.

| 파라미터 | 설정 값 | PX4 내부 설명 및 역할 |
| :--- | :--- | :--- |
| `MAV_1_CONFIG` | `TELEM 2` | MAVLink 1번 인스턴스를 TELEM2 포트에 할당 |
| `MAV_1_MODE` | `Onboard` | 동반 컴퓨터 전용 고속 MAVLink 메시지 프로필 배정 |
| `MAV_1_RATE` | `0` | 자동 대역폭 조절 (0 = 시스템 최적화 주율) |
| `MAV_1_FLOW_CTRL` | `Force off` | 하드웨어 흐름제어 비활성화 (라즈베리파이 미사용) |
| `SER_TEL2_BAUD` | `57600` | TELEM2 포트 통신 속도 (57,600 bps) |

> [!CAUTION]
> `MAV_1_CONFIG` 값을 변경한 후에는 **반드시 비행 컨트롤러를 재부팅(Reboot)**해야 합니다. 재부팅 전에는 `SER_TEL2_BAUD` 등의 세부 파라미터가 목록에 나타나지 않습니다.

### 라즈베리파이측 시리얼 포트 검증

`tools/install.sh` 실행 시 블루투스 비활성화(`dtoverlay=disable-bt`)가 반영되어 하드웨어 UART(PL011)가 GPIO 14/15 핀으로 복구되며 `/dev/serial0`으로 심볼릭 링크됩니다.

* `config.yaml` 기본 MAVLink 설정:

```yaml
mavlink:
  connection: /dev/serial0
  baud: 57600
```

* 포트 매핑 정상 상태 확인:

```bash
ls -l /dev/serial0        # -> ttyAMA0 을 가리켜야 합니다 (ttyS0 이면 BT 비활성화 실패)
```

---

## 4. OFFBOARD 모드 & 위치 추정 파라미터

드론이 하방 카메라의 화면 오차를 수평/수직 속도 명령(`SET_POSITION_TARGET_LOCAL_NED`)으로 받아 제어하려면, FC가 현재 위치와 속도를 인지할 수 있는 GPS 수신 상태가 필수적입니다 (실내 비행 불가).

| 파라미터 | 설정 값 | PX4 역할 및 기능 |
| :--- | :--- | :--- |
| `RC_MAP_FLTMODE` | 모드 채널 번호 | 조종기 모드 스위치가 지정된 RC 채널 배정 |
| `COM_FLTMODE1` ~ `6` | 스위치 슬롯 중 하나를 `Offboard` | 조종기 스위치 위치에 OFFBOARD 모드 할당 |
| `COM_OF_LOSS_T` | `1.0` (초) | MAVLink setpoint 명령 1초 미수신 시 OFFBOARD 이탈 |
| `COM_OBL_RC_ACT` | `Position` | OFFBOARD 이탈 시 조종자가 수동 조종 가능한 Position 모드로 전환 |
| `COM_RCL_EXCEPT` | `0` | OFFBOARD 상태에서도 조종기 신호 두절 시 비상 안전 동작 수행 |
| `MPC_XY_VEL_MAX` | `3` (m/s) | 자율 및 수동 비행 중 최대 수평 속도 한계 제한 |
| `MPC_Z_VEL_MAX_UP` | `1.5` (m/s) | 최대 상승 속도 한계 제한 |
| `MPC_Z_VEL_MAX_DN` | `1.0` (m/s) | 최대 하강 속도 한계 제한 |

### OFFBOARD 진입 필수 조건 (PX4 핵심 메커니즘)

PX4의 OFFBOARD 모드는 **스위치를 전환하기 전부터 MAVLink 속도 setpoint 명령이 최소 2Hz 이상 수신되고 있어야 진입이 승인**됩니다.

```
[조종기 OFFBOARD 스위치 전환]
           ↓
PX4: "최근 MAVLink setpoint가 2Hz 이상 계속 들어오고 있는가?"
           ↓ (No)                         ↓ (Yes)
   모드 전환 거부 (POSCTL 유지)           OFFBOARD 모드 정상 진입
```

* **메인 코드 구현**: `src/track_and_follow.py`는 시동 상태나 모드와 상관없이 **항상 10Hz로 속도 명령을 지속 송신**합니다 (목표를 찾지 못한 동안에도 정지 명령을 계속 송신합니다).
* **DRY RUN 주의**: `safety.dry_run: true` 모드에서는 MAVLink 명령이 실제 송신되지 않으므로 OFFBOARD 진입이 거부됩니다. OFFBOARD 진입을 점검하려면 **프로펠러를 제거한 상태에서 `--live` 옵션으로 실행**해야 합니다.

---

## 5. 필수 안전장치 (Failsafe & Geofence)

| 파라미터 | 설정 값 | 안전장치 동작 |
| :--- | :--- | :--- |
| `GF_ACTION` | `Return` | 지오펜스 한계 이탈 시 자동 귀환(RTL) 수행 |
| `GF_MAX_HOR_DIST` | `30` (m) | 이륙 지점 기준 최대 수평 반경 30m 제한 |
| `GF_MAX_VER_DIST` | `20` (m) | 최대 비행 고도 20m 제한 |
| `NAV_RCL_ACT` | `Return` | 조종기 신호 두절(RC Loss) 시 자동 귀환(RTL) |
| `COM_LOW_BAT_ACT` | `Return at critical, Land at emergency` | 배터리 경고 시 귀환, 비상 수준 시 즉시 착륙 |

> [!WARNING]
> 안전장치 파라미터(`GF_*`, `NAV_RCL_ACT`, `COM_LOW_BAT_ACT`)는 이상 비행 발생 시 기체 분실 및 사고를 막는 최후의 보호막입니다. **절대로 비활성화하거나 값을 과도하게 넓히지 마세요.**

---

## 6. MAVLink 통신 점검 (2단계 점검)

> [!WARNING]
> **프로펠러를 완전히 제거한 상태에서 진행하세요.**

라즈베리파이 터미널에서 2단계 점검 스크립트를 실행합니다:

```bash
python3 tools/check_mavlink.py
```

정상 접속 출력 예시:

```
연결 중: /dev/serial0 @ 57600
하트비트 대기중...
OK! system=1 component=1

mode=POSCTL    armed=False batt=12.4V gps fix=3 sats=11 yaw=+87deg
```

### MAVLink 통신 문제 해결 Guide

| 증상 | 원인 | 확인 및 조치 사항 |
| :--- | :--- | :--- |
| 하트비트 미수신 | TX/RX 배선 오류 | TX/RX 교차(Cross) 연결 재확인 |
| 하트비트 미수신 | FC 재부팅 누락 | `MAV_1_CONFIG=TELEM 2` 설정 후 FC 전원 재부팅 여부 확인 |
| `SER_TEL2_BAUD` 없음 | FC 재부팅 누락 | `MAV_1_CONFIG` 저장 후 FC 재부팅 필수 |
| `Permission denied` | 시리얼 권한 부족 | `sudo usermod -aG dialout pi` 실행 후 재로그인 |
| 데이터 깨짐 / 끊김 | UART 불일치 | `ls -l /dev/serial0`가 `ttyAMA0`을 가리키는지 확인 (`dtoverlay=disable-bt` 누락 점검) |
| `gps fix < 3` | GPS 위성 수신 부족 | 실외 환경으로 이동하여 위성 10개 이상 수신 시까지 대기 |
| `ATTITUDE 대기중` 지속 | MAVLink 프로필 오류 | `MAV_1_MODE`가 `Onboard`로 설정되어 있는지 확인 |

---

다음 → [04. 비행 & 튜닝](04-flight-and-tuning.md)

