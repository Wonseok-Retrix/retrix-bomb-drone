"""IMX500 AI 카메라에서 물체 검출 결과를 읽어오는 모듈.

picamera2 의 imx500_object_detection_demo.py 를 워크샵용으로 정리한 것.
신경망은 카메라 안(IMX500)에서 돌기 때문에 Pi CPU는 거의 놀고 있습니다.
"""

from dataclasses import dataclass

from libcamera import Transform
from picamera2 import Picamera2
from picamera2.devices import IMX500
from picamera2.devices.imx500 import NetworkIntrinsics, postprocess_nanodet_detection


@dataclass
class Detection:
    """검출된 물체 하나. box 는 (x, y, w, h) 픽셀 좌표."""

    label: str
    conf: float
    box: tuple

    @property
    def center(self):
        x, y, w, h = self.box
        return x + w / 2, y + h / 2


class Detector:
    def __init__(self, cfg):
        cam = cfg["camera"]
        det = cfg["detection"]

        # IMX500 은 Picamera2 생성보다 먼저 만들어야 함
        self.imx500 = IMX500(cam["model"])
        intrinsics = self.imx500.network_intrinsics or NetworkIntrinsics()
        intrinsics.task = "object detection"

        with open(cam["labels"]) as f:
            intrinsics.labels = f.read().splitlines()
        if det["postprocess"]:
            intrinsics.postprocess = det["postprocess"]
        intrinsics.bbox_normalization = det["bbox_normalization"]
        intrinsics.bbox_order = det["bbox_order"]
        intrinsics.inference_rate = cam["fps"]
        intrinsics.update_with_defaults()
        self.intrinsics = intrinsics

        self.labels = [l for l in intrinsics.labels if l and l != "-"]
        self.threshold = det["threshold"]
        self.iou = det["iou"]
        self.max_detections = det["max_detections"]

        # 영상을 화면에 그릴 때만 True 로 바꿉니다 (tools/preview.py 가 사용).
        # 비행 중에는 False 라서 프레임을 복사하지 않습니다 = CPU 절약
        self.keep_frame = False
        self.last_frame = None

        self.picam2 = Picamera2(self.imx500.camera_num)
        rotation = cam.get("rotation", 0)
        if rotation not in (0, 180):
            raise ValueError("camera.rotation은 0 또는 180만 지원합니다")
        transform = Transform(hflip=rotation == 180, vflip=rotation == 180)
        config = self.picam2.create_preview_configuration(
            # picamera2 의 포맷 이름은 메모리 바이트 순서의 반대입니다.
            # 즉 "BGR888" 로 잡아야 numpy 배열이 R, G, B 순서가 되어
            # PIL/JPEG 에 그대로 넘길 수 있습니다.
            # 크기를 고정해서 Pi 가 하는 일을 줄입니다.
            main={"format": "BGR888", "size": (640, 480)},
            controls={"FrameRate": intrinsics.inference_rate},
            buffer_count=12,
            transform=transform,
        )
        self.imx500.show_network_fw_progress_bar()
        self.picam2.start(config, show_preview=cam["preview"])
        if intrinsics.preserve_aspect_ratio:
            self.imx500.set_auto_aspect_ratio()

        self.frame_size = self.picam2.camera_configuration()["main"]["size"]

    def read(self):
        """다음 프레임을 기다렸다가 Detection 리스트를 돌려줍니다.

        keep_frame 이 True 면 같은 프레임의 영상을 self.last_frame 에 넣어둡니다.
        (박스와 영상이 반드시 같은 프레임이어야 화면이 어긋나지 않습니다)
        """
        request = self.picam2.capture_request()
        try:
            metadata = request.get_metadata()
            if self.keep_frame:
                self.last_frame = request.make_array("main")
        finally:
            request.release()

        outputs = self.imx500.get_outputs(metadata, add_batch=True)
        if outputs is None:
            return []

        input_w, input_h = self.imx500.get_input_size()

        if self.intrinsics.postprocess == "nanodet":
            from picamera2.devices.imx500.postprocess import scale_boxes

            boxes, scores, classes = postprocess_nanodet_detection(
                outputs=outputs[0],
                conf=self.threshold,
                iou_thres=self.iou,
                max_out_dets=self.max_detections,
            )[0]
            boxes = scale_boxes(boxes, 1, 1, input_h, input_w, False, False)
        else:
            boxes, scores, classes = outputs[0][0], outputs[1][0], outputs[2][0]
            if self.intrinsics.bbox_normalization:
                boxes = boxes / input_h
            if self.intrinsics.bbox_order == "xy":
                boxes = boxes[:, [1, 0, 3, 2]]

        results = []
        for box, score, cls in zip(boxes, scores, classes):
            if score <= self.threshold:
                continue
            idx = int(cls)
            if idx >= len(self.labels):
                continue
            results.append(
                Detection(
                    label=self.labels[idx],
                    conf=float(score),
                    box=self.imx500.convert_inference_coords(box, metadata, self.picam2),
                )
            )
        return results[: self.max_detections]

    def close(self):
        self.picam2.stop()
