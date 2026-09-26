"""Servidor FastAPI de SmartVia (visión).

Coloca `trafico.mp4` / `trafico2.mp4` en la raíz. Cámara 3 (teléfono):

    $env:PHONE_STREAM_URL="http://IP-DEL-TELEFONO:8080/video"
    uvicorn main:app --host 127.0.0.1 --port 8000

El panel PECUU (Next.js) debe estar en :3000 para las alertas.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import config
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
