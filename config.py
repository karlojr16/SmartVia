"""Umbrales y rutas del prototipo SmartVia."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PHONE_STREAM_URL = os.environ.get("PHONE_STREAM_URL", "").strip()

# Videos / streams por cámara.
CAMERAS = {
    "cam1": {
        "key": "cam1",
        "label": "Cámara 1",
        "source": str(BASE_DIR / "trafico.mp4"),
        "camera_id": "Cámara 1 · trafico.mp4",
        "live": False,
    },
    "cam2": {
        "key": "cam2",
        "label": "Cámara 2",
        "source": str(BASE_DIR / "trafico2.mp4"),
        "camera_id": "Cámara 2 · trafico2.mp4",
        "live": False,
    },
    "cam3": {
        "key": "cam3",
        "label": "Cámara 3",
        "source": PHONE_STREAM_URL,
        "camera_id": "Cámara 3 · teléfono",
        "live": True,
    },
    "cam4": {
        "key": "cam4",
        "label": "Cámara 4",
        "source": str(BASE_DIR / "trafico3.mp4"),
        "camera_id": "Cámara 4 · trafico3.mp4",
        "live": False,
    },
    "cam5": {
        "key": "cam5",
        "label": "Cámara 5",
        "source": str(BASE_DIR / "trafico_interseccion.mp4"),
        "camera_id": "Cámara 5 · trafico_interseccion.mp4",
        "live": False,
    },
}
DEFAULT_CAMERA = "cam1"
VIDEO_PATH = Path(CAMERAS[DEFAULT_CAMERA]["source"])
CAMERA_ID = CAMERAS[DEFAULT_CAMERA]["camera_id"]

# YOLOv8 nano (se descarga automáticamente la primera ejecución).
YOLO_MODEL = "yolov8n.pt"

# Clases COCO: car, bus, truck.
VEHICLE_CLASS_IDS = [2, 5, 7]
CONFIDENCE = 0.2

PIXEL_TOLERANCE = 20
STATIONARY_SECONDS = 5.0
JAM_THRESHOLD = 4
ALERT_COOLDOWN_SECONDS = 60.0

JPEG_QUALITY = 80
STREAM_SLEEP_SECONDS = 0.03
INFER_IMGSZ = 320
MAX_FRAME_WIDTH = 640
FRAME_SKIP = 5
LIVE_FRAME_SKIP = 1

# Panel PECUU (Next.js de tu compañero). Recibe POST /api/alerts.
PECUU_ALERTS_URL = "http://127.0.0.1:3000/api/alerts"


def camera_source(cam: dict) -> str:
    return str(cam.get("source") or "").strip()


def capture_target(source: str):
    """Índice de webcam (0) o ruta/URL para OpenCV."""
    if source.isdigit():
        return int(source)
    return source


def open_failure_message(cam: dict) -> str:
    source = camera_source(cam)
    label = cam.get("label", "cámara")
    if cam.get("live"):
        if not source:
            return (
                "Camara 3: define PHONE_STREAM_URL "
                "(ej. http://IP-DEL-TELEFONO:8080/video) y reinicia uvicorn."
            )
        return (
            f"No se pudo abrir el stream de {label}: {source}. "
            "Abre IP Webcam y prueba esa URL en el navegador del PC."
        )
    name = Path(source).name if source else label
    return f"No se pudo abrir {name}. Coloca el video de {label} en la raiz del proyecto."


# Filtro espacial (zonas de circulación, ver zones.py y /calibrate/<cam>).
# Comportamiento cuando una cámara con filtro habilitado no tiene zonas
# calibradas todavía:
#   "all"  -> analizar todo el frame (compatible con el comportamiento previo)
#   "none" -> no analizar ningún vehículo hasta calibrar
ZONE_DEFAULT_MODE = "all"

# El filtro espacial de zonas (calle vs. estacionamiento) y la detección de
# cabeza de fila / cola solo corren para las cámaras en este set. cam3 (el
# teléfono en vivo) queda fuera a propósito: es una cámara de mano que se
# mueve, un polígono fijo no tendría sentido ahí. Agregar una cámara nueva
# aquí basta para habilitarle ambas cosas (previa calibración en
# /calibrate/<cam>) — no hay lógica adicional que duplicar. Una cámara fuera
# de este set no tiene filtro espacial ni cola, y su clasificación
# detenido/movimiento corre sobre el frame completo.
CAMARAS_CON_FILTRO_ZONA = {"cam1", "cam2", "cam4", "cam5"}

# Umbral de agrupamiento de cola: separación máxima (en % de la diagonal del
# frame) entre dos vehículos detenidos consecutivos para considerarlos parte
# de la misma fila continua.
QUEUE_GAP_PERCENT = 6.0
