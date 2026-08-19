#!/usr/bin/env python3
"""검출 결과를 브라우저로 보면서 파라미터를 튜닝합니다.

    python3 tools/preview.py
    python3 tools/preview.py --fps 2          # 화면이 느릴 때
    python3 tools/preview.py --port 8080

실행한 뒤 노트북/휴대폰 브라우저에서 열면 됩니다:

    http://drone.local:8080

Pi 에 모니터를 연결할 필요가 없습니다 (Lite 이미지에서도 동작).

  초록 박스   = 검출된 모든 물체
  빨간 박스   = 현재 추적 중인 목표
  회색 세로띠 = 데드밴드 (이 안에 있으면 좌우 이동 명령 없음)

★ 지상에서 눈으로 확인하는 용도입니다. 비행 중에는 실행하지 마세요.
"""

import argparse
import io
import os
import socket
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from track_and_follow import load_config  # noqa: E402
from controller import Controller  # noqa: E402
from detector import Detector  # noqa: E402
from tracker import Tracker  # noqa: E402

try:
    import simplejpeg  # picamera2 와 함께 설치됨. PIL 보다 빠릅니다.
except ImportError:
    simplejpeg = None


PAGE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>tracking preview</title>
<style>
 body{background:#111;color:#ddd;font-family:sans-serif;text-align:center;margin:0;padding:12px}
 img{max-width:100%;height:auto;border:1px solid #444}
 p{font-size:14px;color:#888}
</style></head>
<body>
<h3>tracking preview</h3>
<img src="/stream.mjpg">
<p>green=detection &nbsp; red=tracked target &nbsp; gray band=deadband<br>
Edit config.yaml, then restart this script.</p>
</body></html>"""


class Stream:
    """가장 최근 JPEG 한 장을 들고 있다가 접속한 브라우저에 나눠줍니다."""

    def __init__(self):
        self._cond = threading.Condition()
        self._frame = None

    def publish(self, jpeg):
        with self._cond:
            self._frame = jpeg
            self._cond.notify_all()

    def wait(self, timeout=5.0):
        with self._cond:
            self._cond.wait(timeout)
            return self._frame


stream = Stream()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/stream.mjpg":
            self.send_response(200)
            self.send_header("Cache-Control", "no-cache")
            self.send_header(
                "Content-Type", "multipart/x-mixed-replace; boundary=FRAME"
            )
            self.end_headers()
            try:
                while True:
                    jpeg = stream.wait()
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(jpeg)))
                    self.end_headers()
                    self.wfile.write(jpeg)
                    self.wfile.write(b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass  # 브라우저 탭이 닫힘. 정상입니다.
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass  # 접속 로그로 콘솔을 더럽히지 않습니다


def encode_jpeg(array, quality=70):
    if simplejpeg is not None:
        return simplejpeg.encode_jpeg(array, quality=quality, colorspace="RGB")
    buf = io.BytesIO()
    Image.fromarray(array).save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "<pi-address>"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fps", type=float, help="temporarily override inference frame rate")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    cfg = load_config(os.path.join(ROOT, "config.yaml"))
    cfg["camera"]["preview"] = False
    if args.fps:
        cfg["camera"]["fps"] = args.fps

    det = Detector(cfg)
    det.keep_frame = True  # read() 가 영상도 같이 챙겨오도록
    trk = Tracker(cfg, det.frame_size)
    ctl = Controller(cfg["control"])
    w, h = det.frame_size
    band = int(cfg["control"]["deadband"] * w / 2)

    server = ThreadingHTTPServer(("", args.port), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()

    print("=" * 52)
    print(f"  Open in browser :  http://{local_ip()}:{args.port}")
    print(f"  Inference fps   :  {cfg['camera']['fps']}")
    print(f"  Camera rotation :  {cfg['camera'].get('rotation', 0)} deg")
    print("  Exit            :  Ctrl+C")
    print("=" * 52)

    try:
        while True:
            detections = det.read()
            target = trk.update(detections)
            # age 를 넘기지 않습니다(=0). 방금 본 프레임 기준의 '온전한' 명령을
            # 보여줘야 부호와 크기를 확인할 수 있기 때문입니다.
            # 비행 중에는 track_and_follow.py 가 나이에 따라 이 값을 줄입니다.
            cmd = ctl.compute(target)

            frame = det.last_frame
            if frame is None:
                continue

            img = Image.fromarray(frame)
            draw = ImageDraw.Draw(img)

            # 화면 중심선 + 데드밴드 영역
            draw.line((w // 2, 0, w // 2, h), fill=(110, 110, 110))
            draw.line((0, h // 2, w, h // 2), fill=(110, 110, 110))
            draw.rectangle(
                (w // 2 - band, 0, w // 2 + band, h - 1), outline=(110, 110, 110)
            )

            for d in detections:
                x, y, bw, bh = d.box
                draw.rectangle((x, y, x + bw, y + bh), outline=(0, 255, 0))
                draw.text((x + 3, y + 3), f"{d.label} {d.conf:.2f}", fill=(0, 255, 0))

            if target is not None:
                x, y, bw, bh = (int(v) for v in target.box)
                draw.rectangle((x, y, x + bw, y + bh), outline=(255, 40, 40), width=3)
                draw.text(
                    (8, h - 14),
                    f"fwd {cmd.forward:+.2f}  right {cmd.right:+.2f}  "
                    f"down {cmd.down:+.2f}  yaw {cmd.yaw_rate:+.0f}  "
                    f"size {target.size:.2f}  conf {target.conf:.2f}",
                    fill=(255, 40, 40),
                )
            else:
                draw.text((8, h - 14), "NO TARGET", fill=(255, 200, 0))

            stream.publish(encode_jpeg(np.asarray(img)))
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.shutdown()
        det.close()


if __name__ == "__main__":
    main()
