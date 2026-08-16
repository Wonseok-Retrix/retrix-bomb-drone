# Object Tracking Drone 워크샵 예제

Raspberry Pi AI Camera(Sony IMX500)로 물체를 감지하고, ArduCopter 기반 자율비행 드론이 이를 추적하도록 구현된 교육용 예제입니다.

---

## 문서 목록 (순서대로 진행)

| 번호 | 문서 | 주요 내용 |
| :--- | :--- | :--- |
| **01** | [하드웨어 & 배선](docs/01-hardware.md) | 주요 부품 구성 및 CSI / UART / 서보 배선 |
| **02** | [라즈베리파이 세팅](docs/02-raspberry-pi.md) | OS 설치, 자동 설치 스크립트 실행, 카메라 점검 및 웹 모니터링 |
| **03** | [비행 컨트롤러 설정](docs/03-flight-controller.md) | ArduCopter 파라미터 설정 및 MAVLink 통신 연결 |
| **04** | [비행 & 튜닝](docs/04-flight-and-tuning.md) | 단계별 비행 검증, 튜닝 가이드, 필수 비행 안전수칙 |
| **05** | [내 모델 만들기](docs/05-custom-model.md) | 데이터 수집, Colab 파인튜닝, .rpk 패키징 및 과녁 자동 투하 |

---

## 빠른 시작

```bash
# 1. 라즈베리파이 초기 설정 (최초 1회만 실행 후 재부팅)
# config.yaml도 config.example.yaml에서 자동 생성됩니다.
bash tools/install.sh && sudo reboot

# 2. 1단계 점검: AI 카메라 작동 확인
python3 tools/check_camera.py

# 3. 2단계 점검: 비행 컨트롤러(FC) MAVLink 통신 확인 (프로펠러 분리 필수)
python3 tools/check_mavlink.py

# 4. 3단계 점검: 서보 드로퍼 동작 확인 (2일차, 책상 위 점검)
python3 tools/check_dropper.py

# 5. 모의 비행 (DRY RUN: 계산만 수행, 실제 명령 전송 없음)
python3 src/track_and_follow.py

# 6. 실전 비행 (docs/04 숙지 후 프로펠러 장착 및 --live 실행)
python3 src/track_and_follow.py --live
```

---

## 파일 구조

```
config.example.yaml           설정 기본값 (Git에서 관리)
config.yaml                   * 장비별 튜닝 파일 (Git에서 제외, 설치 시 생성)
src/
  detector.py                 IMX500 AI 카메라 객체 검출
  tracker.py                  검출 결과 중 단일 목표 선택 및 추적
  command.py                  드론 속도 제어 명령 구조체
  controller.py               하방 카메라 기반 P 제어기 (위치 오차 -> 이동 속도)
  buzzer.py                   패시브 부저 상태음 (GPIO23)
  release.py                  자동 투하 조건 판단
  dropper.py                  서보 드로퍼 구동 (Pi GPIO 직접 제어)
  mavlink_link.py             pymavlink MAVLink 통신 및 안전 상태 점검
  track_and_follow.py         메인 제어 루프
tools/
  install.sh                  라즈베리파이 자동 환경 설정 스크립트
  init_config.sh              config.yaml 최초 생성 (기존 설정은 유지)
  install_autostart.sh        부팅 시 LIVE 모드 자동 실행 서비스 등록
  uninstall_autostart.sh      LIVE 모드 자동 실행 서비스 해제
  check_camera.py             1단계 점검: 카메라 및 AI 모델 작동 테스트
  check_mavlink.py            2단계 점검: FC MAVLink 연결 상태 점검
  test_obc_heartbeat.py       OBC heartbeat/디버그 메시지의 GCS 라우팅 점검
  check_dropper.py            3단계 점검: 서보 드로퍼 각도 및 동작 테스트
  preview.py                  웹 브라우저 기반 실시간 바운딩 박스 및 제어 모니터링
notebooks/
  finetune_imx500_yolo.ipynb  Google Colab 학습 파이프라인 (합성 데이터 생성 -> YOLO 학습 -> 양자화)
assets/
  coco_labels.txt             기본 COCO 모델(80종) 라벨 파일
```

---

## 커리큘럼 (2일 기준)

| 일차 | 일정 | 주요 내용 | 목표 |
| :--- | :--- | :--- | :--- |
| **1일차** | **오전** | 하드웨어 조립, 라즈베리파이 OS 세팅, 기본 모델 물체 검출 점검 | AI 카메라 기반 객체 감지 파이프라인 이해 |
| | **오후** | MAVLink 통신 연결, 모의 비행(DRY RUN), 지상 제어 테스트 및 속도 튜닝 | MAVLink 속도 제어 및 P 제어기 동작 이해 |
| **2일차** | **오전** | 실전 비행 추적 테스트 및 제어 파라미터 최적화 | 지상 목표물 자율 추적 비행 완성 |
| | **오후** | 맞춤 데이터 수집 → Colab 학습 → 커스텀 모델 탑재 및 서보 투하 연동 | 커스텀 과녁 인식 및 자동 물품 투하 비행 완성 |

---

## 참고 자료

- [Raspberry Pi picamera2 — IMX500 예제](https://github.com/raspberrypi/picamera2/tree/main/examples/imx500)
- [Raspberry Pi imx500-models — 기본 모델 목록](https://github.com/raspberrypi/imx500-models)
- [pymavlink 라이브러리 예제](https://github.com/ArduPilot/pymavlink/tree/master/examples)
- [Raspberry Pi AI Camera 공식 문서](https://www.raspberrypi.com/documentation/accessories/ai-camera.html)
- [Ultralytics Sony IMX500 Export 가이드](https://docs.ultralytics.com/integrations/sony-imx500/)
- [ArduPilot Copter — Guided Mode](https://ardupilot.org/copter/docs/ac2_guidedmode.html)
- [ArduPilot — Copter Commands in Guided Mode](https://ardupilot.org/dev/docs/copter-commands-in-guided-mode.html)
- [ArduPilot — MicoAir743v2](https://ardupilot.org/copter/docs/common-MicoAir743v2.html)
