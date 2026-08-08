# Object Tracking Drone 워크샵 예제

Raspberry Pi AI Camera(IMX500)로 물체를 감지하고, ArduPilot 드론이 이를 자율 추적하도록 구현된 교육용 예제입니다.

## 문서 (순서대로 진행)

|     | 문서                                         | 내용                          |
| --- | ------------------------------------------ | --------------------------- |
| 1   | [하드웨어 & 배선](docs/01-hardware.md)           | 주요 부품 안내 및 CSI/UART 배선 방법             |
| 2   | [라즈베리파이 세팅](docs/02-raspberry-pi.md)       | OS 설치, 자동 설치 스크립트 실행, 카메라 작동 점검         |
| 3   | [비행 컨트롤러 설정](docs/03-flight-controller.md) | ArduPilot 파라미터 설정 및 MAVLink 통신 연결  |
| 4   | [비행 & 튜닝](docs/04-flight-and-tuning.md)    | 단계별 비행 테스트, 파라미터 튜닝 표, 필수 안전수칙     |
| 5   | [내 모델 만들기](docs/05-custom-model.md)        | 맞춤 데이터 수집, Colab 학습, .rpk 탑재 방법 |

---

## 빠른 시작

```bash
# 라즈베리파이에서 한 번만
bash tools/install.sh && sudo reboot

# 1) 카메라만 확인
python3 tools/check_camera.py

# 2) 비행 컨트롤러 연결 확인 (프로펠러 뺄 것)
python3 tools/check_mavlink.py

# 2-1) 서보 드로퍼 확인 (2일차, 책상 위에서)
python3 tools/check_dropper.py

# 3) 계산만 (명령 전송 없음)
python3 src/track_and_follow.py

# 4) 실제 비행 (docs/04 를 읽고 나서)
python3 src/track_and_follow.py --live
```

---

## 파일 구조

```
config.yaml                  * 파라미터 튜닝 파일
src/
  detector.py                IMX500 이용 객체 검출
  tracker.py                 여러 검출 중 목표 하나 선택
  command.py                 드론에 보낼 속도 명령 그릇
  controller.py              control.mode 에 맞는 제어기 선택
  controller_front.py        * 전방 카메라 / 사람 따라가기 (P 제어)
  controller_down.py         * 하방 카메라 / 과녁 따라가기 (P 제어)
  release.py                 언제 투하할지 판단
  dropper.py                 서보 드로퍼 (Pi GPIO 직접 제어)
  mavlink_link.py            pymavlink 송수신 + 안전 조건
  track_and_follow.py        메인 루프
tools/
  install.sh                 Pi 설치 스크립트
  check_camera.py            1단계 점검: 카메라
  check_mavlink.py           2단계 점검: 비행 컨트롤러
  check_dropper.py           3단계 점검: 서보 드로퍼
  preview.py                 브라우저로 박스를 보면서 튜닝
notebooks/
  finetune_imx500_yolo.ipynb Colab 파인튜닝 → packerOut.zip
assets/
  coco_labels.txt            기본 모델(COCO 80종) 라벨
```

---

## 커리큘럼 (2일 기준)

|            | 내용                                 | 목표               |
| ---------- | ---------------------------------- | ---------------- |
| **1일차 오전** | 하드웨어 조립, 라즈베리파이 세팅, 기본 모델 기반 `person` 검출 | AI 모델 직접 실행 및 감지 확인    |
| **1일차 오후** | MAVLink 연결, 모의 비행(DRY RUN), 지상 테스트 및 게인 튜닝 | 비행 제어 및 파라미터 기본 이해      |
| **2일차 오전** | 실제 비행 추적 테스트 및 제어 게인 최적화                   | 사람을 자율 추적하는 드론 완성       |
| **2일차 오후** | 맞춤 데이터 수집 → Colab 파인튜닝 → 커스텀 모델 탑재      | 지정 과녁 추적 및 자동 투하 드론 완성 |

---

## 참고

- [raspberrypi/picamera2 — IMX500 예제](https://github.com/raspberrypi/picamera2/tree/main/examples/imx500)
- [raspberrypi/imx500-models — 기본 모델 목록](https://github.com/raspberrypi/imx500-models)
- [ArduPilot/pymavlink — examples](https://github.com/ArduPilot/pymavlink/tree/master/examples)
- [Raspberry Pi AI Camera 문서](https://www.raspberrypi.com/documentation/accessories/ai-camera.html)
- [Ultralytics — Sony IMX500 export](https://docs.ultralytics.com/integrations/sony-imx500/)
- [ArduPilot — MicoAir743v2](https://ardupilot.org/copter/docs/common-MicoAir743v2.html)

