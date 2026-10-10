import cv2
import time
import glob
import logging

log = logging.getLogger("camera")


def detect_cameras() -> list[dict]:
    """
    Находит все USB-камеры через /dev/v4l/by-id/.
    Возвращает список: [{"path": "...", "ok": true, "resolution": [w, h]}, ...]
    Камеры НЕ открываются надолго — только одна короткая проверка.
    """
    paths = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    result = []
    for p in paths:
        item = {"path": p, "ok": False, "resolution": None}
        try:
            cap = cv2.VideoCapture(p, cv2.CAP_V4L2)
            if cap.isOpened():
                ok, frame = cap.read()
                if ok and frame is not None:
                    item["ok"] = True
                    item["resolution"] = [frame.shape[1], frame.shape[0]]
            cap.release()
        except Exception as e:
            log.warning("Ошибка проверки %s: %s", p, e)
        result.append(item)
    return result


class UsbCameraController:
    def __init__(self, cfg):
        self.devices = cfg.devices
        self.width, self.height = cfg.resolution
        self.warmup = cfg.warmup_frames
        self.settle = cfg.settle_sec

    def _source(self, plant_id: int) -> str:
        if not (1 <= plant_id <= len(self.devices)):
            raise ValueError(f"Растение {plant_id}: нет камеры в конфиге")
        return self.devices[plant_id - 1]

    def capture(self, plant_id: int):
        src = self._source(plant_id)
        log.info("Камера plant=%s (%s)", plant_id, src)
        cap = cv2.VideoCapture(src, cv2.CAP_V4L2)
        try:
            if not cap.isOpened():
                raise RuntimeError(f"Не открыть {src}")
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            for _ in range(self.warmup):
                cap.read()
            if self.settle > 0:
                time.sleep(self.settle)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError("Пустой кадр")
            return frame
        finally:
            cap.release()


class RtspCameraController:
    def __init__(self, cfg):
        self.urls = cfg.urls
        self.width, self.height = cfg.resolution
        self.warmup = cfg.warmup_frames
        self.settle = cfg.settle_sec

    def capture(self, plant_id: int):
        url = self.urls[plant_id - 1]
        cap = cv2.VideoCapture(url)
        try:
            if not cap.isOpened():
                raise RuntimeError(f"RTSP {url} недоступен")
            for _ in range(self.warmup):
                cap.read()
            time.sleep(self.settle)
            ok, frame = cap.read()
            if not ok:
                raise RuntimeError("Пустой кадр")
            return frame
        finally:
            cap.release()


def build_camera(cfg):
    return UsbCameraController(cfg) if cfg.type == "usb" else RtspCameraController(cfg)

def force_release_all():
    """Освободить все USB-камеры, если они висят."""
    import glob
    import fcntl
    import os
    for path in glob.glob("/dev/video*"):
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
            try:
                # Попытка эксклюзивного захвата — если получилось, значит камера свободна
                fcntl.ioctl(fd, 0x80045626)  # VIDIOC_QUERYCAP, для проверки
            finally:
                os.close(fd)
        except Exception:
            pass

