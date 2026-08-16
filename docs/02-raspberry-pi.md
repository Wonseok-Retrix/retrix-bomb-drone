# 02. 라즈베리파이 세팅

라즈베리파이 OS(Bookworm Lite) 설치, 필수 소프트웨어 패키지 자동 세팅, AI 카메라 검출 동작 점검 및 브라우저 모니터링 절차입니다.

---

## 1. OS 굽기 (Raspberry Pi Imager)

[Raspberry Pi Imager](https://www.raspberrypi.com/software/)를 사용하여 SD 카드에 OS를 작성합니다.

| 설정 항목 | 선택 값 | 비고 |
| :--- | :--- | :--- |
| **기기** | **Raspberry Pi Zero W** (또는 Zero 2 W) | |
| **OS** | **Raspberry Pi OS Lite (32-bit)** — Bookworm | GUI 불필요 (Zero 2 W는 64-bit Lite 선택 가능) |

⚙️ **설정 (OS 맞춤설정) 세부 항목**:

- **호스트명**: `drone` (네트워크 접속 주소: `drone.local`)
  - **팀별 지정**: 실습 네트워크 충돌 방지를 위해 `drone01`, `drone02` 등으로 서로 다르게 지정하세요.
- **사용자 계정**: 사용자 이름 및 비밀번호 지정 (예: 계정 `pi`)
- **Wi-Fi 설정**: SSID 및 비밀번호 입력
  - **주의**: **반드시 2.4GHz Wi-Fi 대역**이어야 합니다. Zero 계열은 5GHz Wi-Fi를 지원하지 않습니다.
- **SSH 활성화**: **SSH 사용** 옵션 체크

---

## 2. SSH 접속

라즈베리파이에 전원을 연결하고 boot(약 1분) 후 PC 터미널에서 접속합니다.

```bash
ssh pi@drone.local
```

---

## 3. 자동 설치 스크립트 실행

```bash
sudo apt update && sudo apt install -y git
git clone https://github.com/Wonseok-Retrix/retrix-bomb-drone ~/ai-tracking-drone
cd ~/ai-tracking-drone
bash tools/install.sh
sudo reboot
```

`tools/install.sh` 주요 수행 작업:

| 구분 | 패키지 / 설정 | 주요 수행 역할 |
| :--- | :--- | :--- |
| **카메라** | `imx500-all` | IMX500 펌웨어, 기본 COCO 모델(`/usr/share/imx500-models/`), 패키징 툴 |
| **영상 처리** | `python3-picamera2`, `python3-simplejpeg`, `python3-pil` | 카메라 제어 및 경량 영상 렌더링 |
| **의존성** | `python3-opencv` | picamera2 IMX500 모듈 내부 의존성 |
| **통신 / 설정** | `python3-pymavlink`, `python3-yaml`, `python3-pip` | FC MAVLink 통신, `config.yaml` 구조체 읽기, pip3 명령 사용 |
| **UART 복구** | `dtoverlay=disable-bt` | 블루투스를 비활성화하여 하드웨어 UART(PL011)를 GPIO 14/15 핀으로 복구 |
| **시리얼 콘솔** | `raspi-config` | GPIO UART 활성화 및 시리얼 로그인 콘솔 비활성화 |
| **메모리** | `gpu_mem=64` | 헤드리스 운영 환경 메모리 최적화 |

---

## 4. AI 카메라 동작 점검

```bash
cd ~/ai-tracking-drone
python3 tools/check_camera.py
```

* **펌웨어 로딩**: 최초 실행 시 카메라 내부(IMX500)로 AI 모델 펌웨어를 업로드하므로 **1~2분 정도 대기**합니다.
* **정상 로그 예시**:

```
[1.8 fps] person x1, chair x2        | 최고: person 0.83 box=(210, 95, 180, 340)
```

> [!NOTE]
> - 현재 AI 카메라 하드웨어는 **실측 1~2 fps**로 동작합니다. 로그 좌측의 실측 fps가 `config.yaml` 설정값(기본 2 fps) 부근으로 출력되면 정상입니다.
> - 제어기(`controller.py`)는 1~2 fps 피드백 지연 환경을 전제로 감쇠 알고리즘(`stale_hold`/`stale_stop`)과 낮은 `max_*` 속도를 적용하여 오버슈트를 줄이도록 설계되어 있습니다.

### 카메라 문제 해결 Guide

| 증상 | 원인 | 확인 및 조치 사항 |
| :--- | :--- | :--- |
| `No cameras available` | 케이블 접촉 불량 | CSI 케이블 체결 상태 및 금색 접점 방향 확인. `rpicam-hello --list-cameras`로 테스트 |
| `imx500-models` 없음 | 패키지 누락 | `sudo apt install imx500-all` 재실행 |
| `ModuleNotFoundError: cv2` | OpenCV 미설치 | `sudo apt install -y python3-opencv` 실행 |
| 스크립트 실행 중 무한 대기 | 전원 공급 부족 | 라즈베리파이에 정품 5V 3A 이상 전원 어댑터 직접 연결 |
| 검출 프레임이 아예 안 들어옴 | 카메라 스톨 | 전원 재부팅 및 CSI 케이블 재체결 |

---

## 5. 브라우저 실시간 모니터링 & 지상 튜닝 (tools/preview.py)

웹 브라우저를 통해 AI 카메라 검출 영상과 실시간 속도 제어 명령을 확인합니다.

```bash
python3 tools/preview.py --fps 2
```

동일한 Wi-Fi 네트워크의 PC/스마트폰 브라우저에서 아래 주소로 접속합니다:

```
http://drone.local:8080
```

* **초록색 박스**: AI 카메라인 IMX500이 감지한 모든 물체
* **빨간색 박스**: 현재 제어기가 추적 목표로 선택한 물체
* **세로 회색 영역**: 데드밴드 (Deadband, 목표물이 이 영역 내에 있으면 미세 이동 속도 명령을 0으로 억제)
* **하단 빨간색 텍스트**: 현재 계산되어 비행 컨트롤러(FC)로 전송되는 속도 제어 명령(`fwd`, `right`, `down`)

### preview 접속 문제 해결 Guide

| 증상 | 원인 | 해결 방안 |
| :--- | :--- | :--- |
| Wi-Fi 연결 안 됨 | 5GHz AP 접속 시도 | 2.4GHz Wi-Fi 대역 접속 확인 (Zero 계열은 5GHz 미지원) |
| `drone.local` 접속 불가 | mDNS 미지원 환경 | Pi에서 `hostname -I`로 IP 확인 후 `http://192.168.x.x:8080` 접속 |
| SSH는 되나 브라우저만 안 됨 | AP isolation (클라이언트 격리) | 공유기 설정에서 AP isolation 해제 또는 스마트폰 핫스팟 활용 |
| 야외 환경 (공유기 없음) | 네트워크 부재 | 스마트폰 핫스팟(2.4GHz)에 Pi와 노트북을 함께 연결 |

> [!CAUTION]
> `preview.py` 웹 서버는 별도의 인증 절차가 없습니다. 공용 Wi-Fi 환경에서는 지상 튜닝 완료 후 반드시 프로세스를 종료(`Ctrl+C`)하세요.

---

## 6. 부팅 시 추적 프로그램 자동 실행

카메라, MAVLink, 드로퍼를 프로펠러 없이 모두 점검한 뒤 자동 실행 서비스를 등록합니다.

```bash
cd ~/ai-tracking-drone
bash tools/install_autostart.sh
```

서비스는 현재 계정과 저장소 경로를 자동으로 사용하며, 즉시 `track_and_follow.py`를 시작하고 이후 부팅 때마다 자동 실행합니다. 프로세스가 오류로 종료되면 5초 후 재시작합니다.

```bash
systemctl status retrix-bomb-drone.service       # 상태 확인
journalctl -u retrix-bomb-drone.service -f      # 실시간 로그
bash tools/uninstall_autostart.sh                # 중지 및 자동 실행 해제
```

> [!WARNING]
> 이 서비스는 실제 MAVLink 명령과 드로퍼 출력을 활성화합니다. 지상 점검이 끝난 기체에서만 등록하세요. 프로그램은 시동 및 GUIDED 상태를 확인한 뒤 이동 명령을 허용합니다.

---

다음 → [03. 비행 컨트롤러 설정](03-flight-controller.md)
