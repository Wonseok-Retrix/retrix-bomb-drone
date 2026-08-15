# 03. 비행 컨트롤러 설정 (MicoAir 743 v2 / ArduCopter)

비행 컨트롤러와 Mission Planner를 연결하고 ArduCopter, MAVLink 통신, GUIDED 제어 및 안전장치를 설정하는 절차입니다.

---

## 1. 펌웨어 및 GCS 설치

| 항목 | 선택 / 설정 값 | 비고 |
| :--- | :--- | :--- |
| **GCS 소프트웨어** | **Mission Planner** 최신 안정 버전 | [공식 설치 안내](https://ardupilot.org/planner/docs/mission-planner-installation.html) |
| **FC 펌웨어** | **ArduCopter / MicoAir743v2** | 반드시 v2 보드 타겟 사용 |
| **기체 프레임** | **Quad / X** | 실제 모터 배치와 일치시킬 것 |

최초 설치는 부트 버튼을 누른 채 USB를 연결해 DFU 모드로 진입한 다음 `arducopter_with_bl.hex`를 올립니다. 이후 업데이트는 Mission Planner에서 `.apj` 파일로 진행할 수 있습니다.

- [MicoAir743v2 공식 보드 문서](https://ardupilot.org/copter/docs/common-MicoAir743v2.html)
- [MicoAir743v2 안정 펌웨어](https://firmware.ardupilot.org/Copter/stable/MicoAir743v2/)

> [!WARNING]
> PX4 파라미터는 ArduCopter로 이어지지 않습니다. 펌웨어 교체 후 센서, 조종기, 모터 방향, failsafe를 모두 다시 설정하고 프로펠러를 제거한 상태에서 검증하세요.

---

## 2. 필수 캘리브레이션

Mission Planner의 **Setup → Mandatory Hardware**에서 다음 항목을 완료합니다.

1. 가속도계와 수평 자세
2. 나침반
3. 조종기 입력 및 모드 스위치
4. ESC와 모터 순서·회전 방향
5. 배터리 전압·전류 모니터
6. GPS와 EKF 상태

GUIDED 속도 제어에는 유효한 위치 추정이 필요합니다. 기본 구성에서는 실외 GPS 3D Fix와 정상 EKF 상태를 확인한 후 진입하세요.

---

## 3. 시리얼 포트 설정 (Pi 연결)

Pi는 FC의 `UART4`(`SERIAL4`) 에 연결되어 있습니다. GCS 소프트웨어에서 이에 대응하는 파라미터를 다음과 같이 설정해야 합니다.

| 파라미터               | 설정 값 | 역할                         |
| :----------------- | :--- | :------------------------- |
| `SERIAL4_PROTOCOL` | `2`  | MAVLink2                   |
| `SERIAL4_BAUD`     | `57` | 57,600 baud                |
| `SERIAL4_OPTIONS`  | `0`  | 반전·half-duplex 등 특수 옵션 미사용 |

라즈베리파이 설정은 다음과 일치해야 합니다.

```yaml
mavlink:
  connection: /dev/serial0
  baud: 57600
```

```bash
ls -l /dev/serial0        # ttyAMA0을 가리키는지 확인
```

> [!CAUTION]
> 절대 Pi 전원과 FC 전원을 동시에 연결하지 마세요! FC에 배터리를 연결하지 않고 USB로만 전원을 공급할 경우, Pi에 전원 공급이 불안정할 수 있습니다. 

---

## 4. GUIDED 제어 설정

이 프로젝트는 `SET_POSITION_TARGET_LOCAL_NED`를 `MAV_FRAME_BODY_OFFSET_NED` 프레임으로 10Hz 전송합니다. 속도 방향은 기체 기준 전방, 오른쪽, 아래쪽입니다.

OBC의 기본 명령 한계는 좌우·전후 각각 `0.4m/s`, 상승·하강 `0.25m/s`입니다. 수평 한계는 축별 값이므로 대각선 명령의 최대 크기는 약 `0.57m/s`(`sqrt(0.4² + 0.4²)`)입니다.

| ArduCopter 4.7 파라미터 | 시작 권장값    | 역할                           |
| :------------------ | :-------- | :--------------------------- |
| `GUID_TIMEOUT`      | `3.0s`    | 속도 명령이 끊기면 감속·정지하는 시간        |
| `WP_SPD`            | `0.6m/s`  | 대각선 명령을 포함하는 GUIDED 수평 속도 상한 |
| `WP_SPD_UP`         | `0.25m/s` | GUIDED 상승 속도 상한              |
| `WP_SPD_DN`         | `0.25m/s` | GUIDED 하강 속도 상한              |

> [!NOTE]
> ArduCopter 4.6 이하에서는 구버전 파라미터인 `WPNAV_SPEED`, `WPNAV_SPEED_UP`, `WPNAV_SPEED_DN`을 사용하며 단위는 `cm/s`입니다. 구버전에는 각각 `60`, `25`, `25`를 입력합니다.

프로그램은 안전상 스스로 시동하거나 GUIDED로 전환하지 않습니다.

1. LOITER에서 조종자가 시동하고 이륙합니다.
2. `track_and_follow.py --live`를 실행합니다.
3. Mission Planner에서 GUIDED로 전환합니다.
4. 이상 동작 시 조종기 스위치를 LOITER 또는 STABILIZE로 바꿉니다.

GUIDED가 아닌 동안 프로그램은 추적 명령을 차단합니다. GUIDED에서 목표가 없으면 0m/s 정지 명령을 계속 보냅니다.

> [!IMPORTANT]
> `GUID_TIMEOUT`은 명령 단절 시 기체를 정지시키지만 자동으로 LOITER나 RTL로 바꾸지는 않습니다. 조종기·배터리·GCS failsafe와 지오펜스를 별도로 설정해야 합니다.

---

## 5. 안전장치

Mission Planner에서 아래 항목을 실제 비행장과 기체에 맞게 설정하고 각각 동작 시험을 하세요.

| 항목 | 확인 사항 |
| :--- | :--- |
| RC failsafe | 조종기 신호 두절 시 RTL 또는 LAND |
| 배터리 failsafe | Low에서 RTL, Critical에서 LAND 등 단계별 동작 |
| GCS failsafe | Pi heartbeat 단절 시 원하는 동작과 timeout 검증 |
| GeoFence | 최대 고도와 비행 반경, 위반 시 RTL/LAND |
| EKF failsafe | 위치 추정 불량 시 안전 모드 전환 |

안전장치는 책상 위 점검만으로 끝내지 말고, 넓은 장소의 낮은 고도에서 각 상황을 통제된 방식으로 검증하세요.

---

## 6. MAVLink 통신 점검

> [!WARNING]
> 프로펠러를 완전히 제거한 상태에서 진행하세요.

```bash
python3 tools/check_mavlink.py
```

정상 출력 예시:

```text
연결 중: /dev/serial0 @ 57600
하트비트 대기중...
OK! system=1 component=1

mode=LOITER     armed=False batt=12.4V gps fix=3 sats=11 yaw=+87deg
```

| 증상 | 확인 및 조치 |
| :--- | :--- |
| 하트비트 미수신 | TX/RX 교차, 공통 GND, 양쪽 baud 확인 |
| 하트비트 미수신 | 연결 UART에 대응하는 `SERIALx_PROTOCOL=2`인지 확인 |
| `UNSUPPORTED_AUTOPILOT` | MicoAir743v2에 ArduCopter 펌웨어가 설치됐는지 확인 |
| `GUIDED 아님` 지속 | GPS/EKF 상태 확인 후 Mission Planner에서 GUIDED 전환 |
| 배터리·GPS·ATTITUDE 누락 | `SERIALx` stream rate와 메시지 요청 응답 확인 |
| `Permission denied` | `sudo usermod -aG dialout pi` 후 재로그인 |

---

다음 → [04. 비행 & 튜닝](04-flight-and-tuning.md)
