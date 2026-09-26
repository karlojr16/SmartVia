"""Servidor FastAPI de SmartVia (visión).

Coloca `trafico.mp4` en la raíz. El panel PECUU (Next.js) debe estar en :3000
para recibir las alertas de embotellamiento:

    npm install
    npm run dev

    uvicorn main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

import config
from tracker import TrafficAnalyzer

analyzer = TrafficAnalyzer()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))


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
        {"video_name": config.VIDEO_PATH.name},
    )


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
