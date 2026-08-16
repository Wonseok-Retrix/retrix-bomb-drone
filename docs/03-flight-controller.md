# 03. 비행 컨트롤러 설정 (MicoAir 743 v2 / ArduCopter)

비행 컨트롤러와 Mission Planner를 연결하고 ArduCopter, MAVLink 통신, AltHold RC override 및 안전장치를 설정하는 절차입니다.

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
6. 기압계와 EKF 상태

AltHold는 GPS 없이 기압계와 IMU로 고도를 유지합니다. GPS가 없으면 수평 위치는
유지되지 않으며, OBC와 조종자 모두 스틱을 놓은 동안 바람에 따라 드리프트할 수 있습니다.

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
  source_system: 255
  source_component: 191
  status_interval: 5
```

```bash
ls -l /dev/serial0        # ttyAMA0을 가리키는지 확인
```

> [!CAUTION]
> 절대 Pi 전원과 FC 전원을 동시에 연결하지 마세요! FC에 배터리를 연결하지 않고 USB로만 전원을 공급할 경우, Pi에 전원 공급이 불안정할 수 있습니다. 

---

## 4. AltHold RC override 설정

이 프로젝트는 `RC_CHANNELS_OVERRIDE`를 10Hz로 전송해 AltHold의 roll, pitch,
throttle, yaw 입력을 대신합니다. GPS 위치 명령은 사용하지 않습니다. OBC 명령은
`control.max_*`의 명령을 축별 `*_pwm_per_unit` 게인으로 PWM 편차로 바꾸고,
`mavlink.rc_override.pwm_span`에서 최종 편차를 제한합니다.

throttle도 override하므로 목표가 작으면 하강하고 목표가 너무 크면 상승합니다.
목표가 없거나 크기 오차가 데드밴드 안이면 중립 throttle을 보내 AltHold가 현재
고도를 유지합니다. `control.max_vertical: 0`이면 자동 상승·하강이 꺼집니다.

Mission Planner의 Full Parameter Tree에서 다음을 설정합니다.

| ArduCopter 파라미터 | 설정값 | 역할 |
| :--- | :--- | :--- |
| `MAV_GCS_SYSID` | `255` | 이 SYSID에서 온 RC override만 허용 |
| `RC8_OPTION` | `46` | CH8 스위치로 RC override 허용/차단 |
| `RC_OVERRIDE_TIME` | `0.5s` | OBC 명령 단절 시 실제 수신기 입력으로 복귀 |

사용하는 보조 채널이 CH8이 아니면 `RCx_OPTION=46`과 `config.yaml`의
`enable_channel`을 같은 채널로 바꿉니다.

프로그램은 스스로 시동하거나 비행 모드를 바꾸지 않으며 현재 모드도 검사하지 않습니다.

1. 조종자가 직접 AltHold를 선택하고 시동·이륙합니다.
2. `track_and_follow.py`를 실행합니다.
3. CH8 override 허용 스위치를 HIGH로 올립니다.
4. 이상 동작 시 CH8을 LOW로 내려 즉시 제어권을 회수합니다.

CH8이 LOW이거나 disarmed 상태이면 프로그램은 override를 해제합니다. 목표가 없으면
중립 PWM을 보냅니다. override 중에는 RC1~RC4 실제 스틱 입력이 무시됩니다.
OBC가 비행 모드와 시작 전 스틱 위치를 검증하지 않으므로 AltHold 선택과 CH8 조작은
전적으로 조종자가 확인해야 합니다.

> [!IMPORTANT]
> ArduCopter 4.7에서는 주 스틱을 움직여도 override가 자동 해제되지 않습니다.
> 프로펠러를 제거한 상태에서 CH8 LOW 시 RC1~RC4가 실제 조종기 입력으로 즉시
> 돌아오는지 먼저 검증하세요.

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
| `RC_OVERRIDE_DISABLED` 지속 | `RC8_OPTION=46` 확인 후 CH8 스위치를 HIGH로 전환 |
| 배터리·GPS·ATTITUDE 누락 | `SERIALx` stream rate와 메시지 요청 응답 확인 |
| `Permission denied` | `sudo usermod -aG dialout pi` 후 재로그인 |

---

다음 → [04. 비행 & 튜닝](04-flight-and-tuning.md)
