"""Umbrales y rutas del prototipo SmartVia."""

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# Videos de entrada por cámara.
CAMERAS = {
    "cam1": {
        "key": "cam1",
        "label": "Cámara 1",
        "path": BASE_DIR / "trafico.mp4",
        "camera_id": "Cámara 1 · trafico.mp4",
    },
    "cam2": {
        "key": "cam2",
        "label": "Cámara 2",
        "path": BASE_DIR / "trafico2.mp4",
        "camera_id": "Cámara 2 · trafico2.mp4",
    },
}
DEFAULT_CAMERA = "cam1"
VIDEO_PATH = CAMERAS[DEFAULT_CAMERA]["path"]
CAMERA_ID = CAMERAS[DEFAULT_CAMERA]["camera_id"]

# YOLOv8 nano (se descarga automáticamente la primera ejecución).
YOLO_MODEL = "yolov8n.pt"

# Clases COCO: car, bus, truck.
VEHICLE_CLASS_IDS = [2, 5, 7]

PIXEL_TOLERANCE = 20
STATIONARY_SECONDS = 5.0
JAM_THRESHOLD = 4
ALERT_COOLDOWN_SECONDS = 60.0

JPEG_QUALITY = 80
STREAM_SLEEP_SECONDS = 0.03
INFER_IMGSZ = 320
MAX_FRAME_WIDTH = 640
FRAME_SKIP = 5

# Panel PECUU (Next.js de tu compañero). Recibe POST /api/alerts.
PECUU_ALERTS_URL = "http://127.0.0.1:3000/api/alerts"
