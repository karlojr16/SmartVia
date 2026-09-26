"""Análisis YOLOv8 + ByteTrack y detección de embotellamiento estático."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import hypot
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO

import config
from firebase_notifier import send_jam_alert

COLOR_MOVING = (46, 204, 113)
COLOR_STATIONARY = (50, 50, 230)
COLOR_OVERLAY = (20, 20, 20)


@dataclass
class TrackMemory:
    cx: float
    cy: float
    last_move_ts: float
    stationary: bool = False


@dataclass
class SharedState:
    lock: threading.Lock = field(default_factory=threading.Lock)
    jpeg: bytes = b""
    jam: bool = False
    vehicle_count: int = 0
    stationary_count: int = 0
    last_alert_at: str | None = None
    error: str | None = None
    camera_key: str = "cam1"
    camera_id: str = ""
    camera_label: str = "Cámara 1"


class TrafficAnalyzer:
    def __init__(self) -> None:
        self.state = SharedState()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._tracks: dict[int, TrackMemory] = {}
        self._last_alert_ts: dict[str, float] = {}
        self._model: YOLO | None = None
        self._requested_camera = config.DEFAULT_CAMERA
        self._camera_lock = threading.Lock()
        cam = config.CAMERAS[config.DEFAULT_CAMERA]
        self.state.camera_key = cam["key"]
        self.state.camera_id = cam["camera_id"]
        self.state.camera_label = cam["label"]
        placeholder = self._placeholder_frame("Cargando modelo YOLOv8...")
        ok, buf = cv2.imencode(".jpg", placeholder)
        if ok:
            self.state.jpeg = buf.tobytes()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="smartvia-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def snapshot_status(self) -> dict[str, Any]:
        with self.state.lock:
            return {
                "jam": self.state.jam,
                "vehicle_count": self.state.vehicle_count,
                "stationary_count": self.state.stationary_count,
                "last_alert_at": self.state.last_alert_at,
                "error": self.state.error,
                "camera_key": self.state.camera_key,
                "camera_id": self.state.camera_id,
                "camera_label": self.state.camera_label,
            }

    def latest_jpeg(self) -> bytes:
        with self.state.lock:
            return self.state.jpeg

    def set_camera(self, camera_key: str) -> dict[str, Any]:
        if camera_key not in config.CAMERAS:
            raise ValueError(f"Cámara desconocida: {camera_key}")
        with self._camera_lock:
            self._requested_camera = camera_key
        return {"ok": True, "camera_key": camera_key}

    def _current_request(self) -> str:
        with self._camera_lock:
            return self._requested_camera

    def _open_capture(self, camera_key: str):
        cam = config.CAMERAS[camera_key]
        source = config.camera_source(cam)
        if not source:
            cap = cv2.VideoCapture("__smartvia_no_source__")
        else:
            target = config.capture_target(source)
            if isinstance(target, int):
                cap = cv2.VideoCapture(target, cv2.CAP_DSHOW)
            else:
                cap = cv2.VideoCapture(target)
        with self.state.lock:
            self.state.camera_key = cam["key"]
            self.state.camera_id = cam["camera_id"]
            self.state.camera_label = cam["label"]
        self._tracks.clear()
        try:
            if self._model and self._model.predictor and self._model.predictor.trackers:
                self._model.predictor.trackers[0].reset()
        except Exception:
            pass
        return cap, cam

    def _fail_open(self, cam: dict) -> None:
        msg = config.open_failure_message(cam)
        self._set_error(msg)
        placeholder = self._placeholder_frame(msg)
        self._publish_frame(placeholder, 0, 0, False, clear_error=False)

    def _run(self) -> None:
        cap = None
        camera_key = self._current_request()
        try:
            self._model = YOLO(config.YOLO_MODEL)
            cap, cam = self._open_capture(camera_key)
            if not cap.isOpened():
                self._fail_open(cam)

            while not self._stop.is_set():
                requested = self._current_request()
                if requested != camera_key or cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    camera_key = requested
                    cap, cam = self._open_capture(camera_key)
                    if not cap.isOpened():
                        self._fail_open(cam)
                        time.sleep(0.4)
                        continue

                skip = config.LIVE_FRAME_SKIP if cam.get("live") else config.FRAME_SKIP
                for _ in range(skip):
                    cap.grab()
                ok, frame = cap.read()
                if not ok:
                    self._tracks.clear()
                    try:
                        if self._model.predictor and self._model.predictor.trackers:
                            self._model.predictor.trackers[0].reset()
                    except Exception:
                        pass
                    if cam.get("live"):
                        cap.release()
                        time.sleep(0.5)
                        cap, cam = self._open_capture(camera_key)
                        continue
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue

                h, w = frame.shape[:2]
                if w > config.MAX_FRAME_WIDTH:
                    scale = config.MAX_FRAME_WIDTH / w
                    frame = cv2.resize(frame, (config.MAX_FRAME_WIDTH, int(h * scale)))

                annotated, vehicles, stationary, jam = self._process_frame(frame)
                self._maybe_alert(jam, vehicles, stationary, cam["camera_id"])
                self._publish_frame(annotated, vehicles, stationary, jam)
        except Exception as exc:  # noqa: BLE001 — el hilo no debe morir en silencio
            self._set_error(str(exc))
        finally:
            if cap is not None:
                cap.release()

    def _process_frame(
        self, frame: np.ndarray
    ) -> tuple[np.ndarray, int, int, bool]:
        assert self._model is not None
        now = time.monotonic()
        results = self._model.track(
            frame,
            persist=True,
            verbose=False,
            classes=config.VEHICLE_CLASS_IDS,
            tracker="bytetrack.yaml",
            imgsz=config.INFER_IMGSZ,
            conf=config.CONFIDENCE,
        )
        result = results[0]
        annotated = frame.copy()
        seen: set[int] = set()
        stationary_ids: set[int] = set()

        boxes = result.boxes
        if boxes is not None and boxes.id is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int)
            for box, track_id in zip(xyxy, ids):
                x1, y1, x2, y2 = box
                cx = float((x1 + x2) / 2)
                cy = float((y1 + y2) / 2)
                seen.add(int(track_id))
                mem = self._tracks.get(int(track_id))
                if mem is None:
                    self._tracks[int(track_id)] = TrackMemory(cx=cx, cy=cy, last_move_ts=now)
                    is_stat = False
                else:
                    dist = hypot(cx - mem.cx, cy - mem.cy)
                    if dist > config.PIXEL_TOLERANCE:
                        mem.last_move_ts = now
                        mem.stationary = False
                    mem.cx, mem.cy = cx, cy
                    is_stat = (now - mem.last_move_ts) >= config.STATIONARY_SECONDS
                    mem.stationary = is_stat
                if is_stat:
                    stationary_ids.add(int(track_id))
                self._draw_vehicle(annotated, box, int(track_id), is_stat)

        for tid in list(self._tracks):
            if tid not in seen:
                del self._tracks[tid]

        vehicle_count = len(seen)
        stationary_count = len(stationary_ids)
        jam = stationary_count >= config.JAM_THRESHOLD
        self._draw_overlay(annotated, vehicle_count, stationary_count, jam)
        return annotated, vehicle_count, stationary_count, jam

    def _maybe_alert(
        self, jam: bool, vehicle_count: int, stationary_count: int, camera_id: str
    ) -> None:
        if not jam:
            return
        now = time.monotonic()
        last = self._last_alert_ts.get(camera_id, 0.0)
        if now - last < config.ALERT_COOLDOWN_SECONDS:
            return
        self._last_alert_ts[camera_id] = now
        detected_at = datetime.now(timezone.utc).isoformat()
        send_jam_alert(
            {
                "title": f"SmartVia: embotellamiento en {camera_id}",
                "body": (
                    f"{stationary_count} vehículos estacionarios "
                    f"(total {vehicle_count}). Posible choque o congestionamiento."
                ),
                "camera_id": camera_id,
                "vehicle_count": vehicle_count,
                "stationary_count": stationary_count,
                "detected_at": detected_at,
                "severity": (
                    f"CRITICAL — {stationary_count} stationary / "
                    f"{vehicle_count} vehicles (possible collision)"
                ),
            }
        )
        with self.state.lock:
            self.state.last_alert_at = detected_at

    def _publish_frame(
        self,
        frame: np.ndarray,
        vehicles: int,
        stationary: int,
        jam: bool,
        clear_error: bool = True,
    ) -> None:
        ok, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY]
        )
        if not ok:
            return
        with self.state.lock:
            self.state.jpeg = buf.tobytes()
            self.state.vehicle_count = vehicles
            self.state.stationary_count = stationary
            self.state.jam = jam
            if clear_error:
                self.state.error = None

    def _set_error(self, message: str) -> None:
        with self.state.lock:
            self.state.error = message
        print(f"[SmartVia] {message}")

    def _draw_vehicle(self, frame: np.ndarray, box: np.ndarray, track_id: int, stationary: bool) -> None:
        x1, y1, x2, y2 = map(int, box)
        color = COLOR_STATIONARY if stationary else COLOR_MOVING
        label = f"{track_id} {'S' if stationary else 'M'}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.35
        thickness = 1
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 1)
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        pad = 2
        # Etiqueta dentro de la caja para no tapar vehículos vecinos.
        tx = x1 + pad
        ty = y1 + th + pad + 1
        bg_y1 = y1
        bg_y2 = min(y2, y1 + th + pad * 2 + 2)
        if bg_y2 - bg_y1 < th:
            bg_y1 = max(0, y1 - th - pad * 2)
            bg_y2 = y1
            ty = y1 - pad
        cv2.rectangle(frame, (tx - pad, bg_y1), (min(x2, tx + tw + pad), bg_y2), color, -1)
        cv2.putText(
            frame,
            label,
            (tx, ty),
            font,
            scale,
            (255, 255, 255),
            thickness,
            cv2.LINE_AA,
        )

    def _draw_overlay(self, frame: np.ndarray, vehicles: int, stationary: int, jam: bool) -> None:
        _h, w = frame.shape[:2]
        status = "EMBOTELLAMIENTO" if jam else "TRAFICO FLUIDO"
        cam_label = self.state.camera_label
        text = f"{cam_label} | {status} | veh={vehicles} stop={stationary}"
        cv2.rectangle(frame, (0, 0), (w, 36), COLOR_OVERLAY, -1)
        cv2.putText(
            frame,
            text,
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            COLOR_STATIONARY if jam else COLOR_MOVING,
            2,
            cv2.LINE_AA,
        )

    def _placeholder_frame(self, message: str) -> np.ndarray:
        frame = np.zeros((480, 854, 3), dtype=np.uint8)
        words = message.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if len(trial) > 70:
                if current:
                    lines.append(current)
                current = word
            else:
                current = trial
        if current:
            lines.append(current)
        y = 200
        for line in lines[:6]:
            cv2.putText(
                frame,
                line,
                (24, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (200, 200, 200),
                1,
                cv2.LINE_AA,
            )
            y += 32
        return frame
