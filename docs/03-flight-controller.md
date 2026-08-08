# 03. 비행 컨트롤러 설정 (MicoAir 743 v2 / ArduPilot)

비행 컨트롤러(FC)를 컴퓨터와 USB로 연결하고 QGroundControl 프로그램으로 파라미터를 설정합니다.

## 1. 펌웨어 및 GCS 소프트웨어

* 비행 컨트롤러에는 ArduPilot 펌웨어가 기본 설치되어 있습니다.
* 펌웨어 버전은 **ArduPilot Copter 4.5 이상**, 보드 타겟은 `MicoAir743v2`입니다.
* GCS(지상통제소) 소프트웨어인 QGroundControl을 설치하세요. ([다운로드 링크](https://qgroundcontrol.com/))
* Mission Planner 사용 시 Setup → Install Firmware 메뉴에서 해당 보드를 선택하면 적합한 펌웨어가 자동 인식됩니다.

## 2. 필수 캘리브레이션

아래 센서 캘리브레이션을 순서대로 반드시 완료해야 합니다. 과정을 하나라도 누락하면 GUIDED 비행 모드 진입이 승인되지 않습니다.

1. Accel Calibration (6면)
2. Compass Calibration
3. Radio Calibration
4. ESC Calibration
5. Battery Monitor

## 3. 시리얼 포트 (Pi 연결)

MicoAir 743 v2의 **TELEM2 커넥터는 ArduPilot 내부 파라미터의 SERIAL4**에 해당합니다.

| 파라미터               | 값    | 의미                         |
| ------------------ | ---- | -------------------------- |
| `SERIAL4_PROTOCOL` | `2`  | MAVLink2 통신 프로토콜 적용     |
| `SERIAL4_BAUD`     | `57` | 57600 bps 속도 설정         |
| `SERIAL4_OPTIONS`  | `0`  | 하드웨어 흐름제어 비활성화 (Pi 미사용) |
| `BRD_SER4_RTSCTS`  | `0`  | 상동 (RTS/CTS 비활성화)       |

### 라즈베리파이측 UART 설정 (Zero W 필수 사항)

Raspberry Pi Zero W 및 Zero 2 W는 **블루투스 모듈이 성능이 안정적인 하드웨어 UART(PL011)를 기본 점유**하고 있습니다.
이 설정을 변경하지 않으면 GPIO 14/15 핀에 mini UART가 할당되는데,
mini UART는 전용 클럭이 없어 **CPU 클럭 변동에 따라 보드레이트가 불안정해집니다.**
이는 MAVLink 통신 데이터를 간헐적으로 손상시키는 주된 원인이 됩니다.

`tools/install.sh` 스크립트를 실행하면 블루투스가 자동으로 비활성화되고 UART 설정이 정상화됩니다.

```
enable_uart=1
dtoverlay=disable-bt      # 블루투스를 꺼서 PL011 을 GPIO 14/15 로 되돌림
```

설정 완료 후에는 `/dev/serial0` 포트를 통해 시리얼 통신을 진행할 수 있습니다. UART 설정은 `config.yaml` 파일에서 지정할 수 있으며 기본값은 다음과 같습니다:

```yaml
mavlink:
  connection: /dev/serial0
  baud: 57600
```

통신 포트 연결 확인:

```bash
ls -l /dev/serial0        # -> ttyAMA0 을 가리켜야 합니다 (ttyS0 이면 설정 실패)
```

## 4. GUIDED 모드 & 위치 추정

본 예제는 비행 컨트롤러로 **속도 제어 명령(SET_POSITION_TARGET_LOCAL_NED)** 을 전송합니다.
기체가 자신의 이동 속도를 정확히 인지해야 하므로 GPS 수신이 필수적입니다. 따라서 실내에서는 비행 테스트가 불가능합니다.

| 파라미터 | 값 | 의미 |
|---|---|---|
| `FLTMODE1` ~ `FLTMODE6` | 스위치 위치 중 하나를 `4` (GUIDED)로 지정 | 조종기 모드 스위치에 GUIDED 배정 |
| `WPNAV_SPEED` | `300` | GUIDED 모드 최대 수평속도 300cm/s 제한 |
| `WPNAV_SPEED_UP/DN` | `150` / `100` | 상승/하강 속도 제한 |
| `GUID_TIMEOUT` | `3` | 3초간 명령 미수신 시 자동 정지 (기본값) |

## 5. 필수 안전장치 설정

| 파라미터              | 값    | 의미             |
| ----------------- | ---- | -------------- |
| `FENCE_ENABLE`    | `1`  | 지오펜스 활성화       |
| `FENCE_TYPE`      | `3`  | 고도 + 반경 경계 적용  |
| `FENCE_ALT_MAX`   | `20` | 최대 고도 20m 제한   |
| `FENCE_RADIUS`    | `30` | 이륙 지점 기준 반경 30m 제한 |
| `FENCE_ACTION`    | `1`  | 경계 이탈 시 RTL(자동 귀환) 수행 |
| `FS_THR_ENABLE`   | `1`  | 조종기 신호 두절 시 RTL 수행 |
| `BATT_FS_LOW_ACT` | `2`  | 저전압 경고 발생 시 RTL 수행 |

제어 코드에 오류가 발생하여 기체가 비정상적으로 비행하더라도, 지오펜스가 설정되어 있으면 기체가 이탈 영역 밖으로 멀리 비행하는 것을 방지할 수 있습니다.
**안전장치 파라미터는 절대로 비활성화하지 마세요.**

## 6. 연결 확인

프로펠러를 **반드시 완전히 분리한 상태**에서 라즈베리파이 터미널에 다음 명령을 입력하세요:

```bash
python3 tools/check_mavlink.py
```

```
연결 중: /dev/serial0 @ 57600
하트비트 대기중...
OK! system=1 component=1

mode=STABILIZE armed=False batt=12.4V gps fix=3 sats=11 yaw=+87deg
```

### 문제 해결 (연결이 안 될 때)

| 증상                  | 확인 및 조치 사항                                                            |
| ------------------- | --------------------------------------------------------------------- |
| 하트비트 신호 미수신         | TX/RX 교차 배선 상태 확인. 배선 교체 후 다시 시도                                       |
| 하트비트 신호 미수신         | `SERIAL4_PROTOCOL=2` 파라미터 저장 후 비행 컨트롤러를 재부팅했는지 확인                       |
| `Permission denied` | `sudo usermod -aG dialout pi` 명령 실행 후 재로그인                                |
| 문자 깨짐 현상 발생        | 통신 보드레이트 불일치. 양측 모두 57600으로 설정되어 있는지 확인                              |
| 통신 불안정 (간헐적 연결)     | `ls -l /dev/serial0` 실행 시 `ttyS0`을 가리키는 경우 → `dtoverlay=disable-bt` 누락됨. 재부팅 필요 |
| `/dev/serial0` 장치 없음 | `install.sh` 스크립트의 시리얼 관련 설정 단계 재실행 및 재부팅                              |
| `gps fix < 3`       | 실외 환경으로 이동하여 위성 신호가 10개 이상 수신될 때까지 대기                                |

---

다음 → [04. 비행 & 튜닝](04-flight-and-tuning.md)

