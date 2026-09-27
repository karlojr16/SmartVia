"""Servidor FastAPI de SmartVia (visión).

Coloca `trafico.mp4` / `trafico2.mp4` / `trafico3.mp4` en la raíz. Cámara 3 (teléfono):

    $env:PHONE_STREAM_URL="http://IP-DEL-TELEFONO:8080/video"
    uvicorn main:app --host 127.0.0.1 --port 8000

El panel PECUU (Next.js) debe estar en :3000 para las alertas.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
import zones as zone_store
from tracker import TrafficAnalyzer

analyzer = TrafficAnalyzer()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


class CameraSelect(BaseModel):
    camera: str


@asynccontextmanager
async def lifespan(_app: FastAPI):
    analyzer.start()
    yield
    analyzer.stop()


app = FastAPI(title="SmartVia", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "cameras": [
                {"key": key, "label": cam["label"]}
                for key, cam in config.CAMERAS.items()
            ],
            "active_camera": config.DEFAULT_CAMERA,
        },
    )


@app.post("/api/camera")
async def select_camera(body: CameraSelect):
    try:
        analyzer.set_camera(body.camera)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return analyzer.snapshot_status()


@app.get("/api/status")
async def status():
    return analyzer.snapshot_status()


def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        jpeg = analyzer.latest_jpeg()
        if jpeg:
            yield (
                boundary
                + b"\r\nContent-Type: image/jpeg\r\nContent-Length: "
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
        time.sleep(config.STREAM_SLEEP_SECONDS)


@app.get("/video")
async def video_feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ---------------------------------------------------------------------------
# Calibración de zonas de circulación (filtro espacial, ver zones.py).
# ---------------------------------------------------------------------------


@app.get("/calibrate/{camera_key}", response_class=HTMLResponse)
async def calibrate_page(request: Request, camera_key: str):
    if camera_key not in config.CAMERAS:
        raise HTTPException(status_code=404, detail=f"Cámara desconocida: {camera_key}")
    return templates.TemplateResponse(
        request,
        "calibrate.html",
        {
            "camera_key": camera_key,
            "cameras": [
                {"key": key, "label": cam["label"]}
                for key, cam in config.CAMERAS.items()
            ],
        },
    )


@app.get("/calibrate/{camera_key}/frame.jpg")
def calibrate_frame(camera_key: str, frame_no: int = 30):
    """Frame de referencia para el editor de polígonos.

    BUG corregido: esta ruta hacía trabajo de OpenCV bloqueante
    (VideoCapture/set/read) dentro de un handler `async def`, lo que
    congelaba el único event loop de FastAPI mientras corría — y con él,
    el stream MJPEG de /video (que se ve como si el video se "pausara" en
    una imagen fija). Al ser ahora un `def` normal, FastAPI la despacha
    a un threadpool y el event loop queda libre.

    Además, para cam3 (teléfono en vivo) NUNCA se abre una segunda
    VideoCapture sobre el mismo stream: muchas apps tipo IP Webcam solo
    aceptan un cliente conectado, y un `cap.set(POS_FRAMES, ...)` sobre un
    stream en vivo no tiene sentido (no es seekable) y puede colgarse. En
    su lugar, se reutiliza el último frame que ya decodificó el hilo del
    analizador para esa cámara.
    """
    if camera_key not in config.CAMERAS:
        raise HTTPException(status_code=404, detail=f"Cámara desconocida: {camera_key}")
    cam = config.CAMERAS[camera_key]

    if cam.get("live"):
        status = analyzer.snapshot_status()
        if status.get("camera_key") != camera_key:
            analyzer.set_camera(camera_key)
            for _ in range(20):  # hasta ~5s para que el hilo conecte y decodifique
                time.sleep(0.25)
                status = analyzer.snapshot_status()
                if status.get("camera_key") == camera_key:
                    break
        jpeg = analyzer.latest_jpeg()
        if not jpeg:
            raise HTTPException(
                status_code=503,
                detail="Sin frame disponible todavía para esta cámara en vivo",
            )
        return Response(content=jpeg, media_type="image/jpeg")

    source = config.camera_source(cam)
    if not source:
        raise HTTPException(status_code=500, detail=config.open_failure_message(cam))
    target = config.capture_target(source)
    cap = cv2.VideoCapture(target)
    try:
        if not cap.isOpened():
            raise HTTPException(status_code=500, detail=config.open_failure_message(cam))
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_no)
        ok, frame = cap.read()
        if not ok:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok:
            raise HTTPException(status_code=500, detail="No se pudo leer un frame del video")
    finally:
        cap.release()

    h, w = frame.shape[:2]
    if w > config.MAX_FRAME_WIDTH:
        scale = config.MAX_FRAME_WIDTH / w
        frame = cv2.resize(frame, (config.MAX_FRAME_WIDTH, int(h * scale)))
    ok, buf = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(status_code=500, detail="No se pudo codificar el frame")
    return Response(content=buf.tobytes(), media_type="image/jpeg")


@app.get("/api/zones/{camera_key}")
async def get_zones(camera_key: str):
    if camera_key not in config.CAMERAS:
        raise HTTPException(status_code=404, detail=f"Cámara desconocida: {camera_key}")
    return zone_store.read_raw(camera_key)


@app.post("/api/zones/{camera_key}")
async def post_zones(camera_key: str, body: dict[str, Any] = Body(...)):
    if camera_key not in config.CAMERAS:
        raise HTTPException(status_code=404, detail=f"Cámara desconocida: {camera_key}")
    saved = zone_store.save_zones(camera_key, body)
    return {"ok": True, "saved": saved}
