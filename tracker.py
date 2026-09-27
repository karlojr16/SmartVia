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
from queue_analysis import EMPTY_QUEUE, QueueResult, build_queue
from zones import CameraZones, bottom_center, load_zones

COLOR_MOVING = (46, 204, 113)
# "Detenido" genérico: vehículo quieto dentro de la zona de calle que no
# forma parte de una cola reconocida (ver deprecación de "parked" abajo).
COLOR_STOPPED = (50, 50, 230)
COLOR_EXCLUDED = (110, 110, 110)
COLOR_ZONE_OUTLINE = (0, 200, 255)
COLOR_QUEUE_HEAD = (0, 0, 255)      # rojo fuerte — cabeza de fila
COLOR_QUEUE_MEMBER = (0, 140, 255)  # naranja — resto de la cola
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
    queue_head_id: int | None = None
    queue_members: list[int] = field(default_factory=list)
    queue_length: int = 0
    queue_length_px: float = 0.0


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
                "queue_head_id": self.state.queue_head_id,
                "queue_members": list(self.state.queue_members),
                "queue_length": self.state.queue_length,
                "queue_length_px": self.state.queue_length_px,
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

    def _frame_interval(self, cap, skip: int) -> float:
        fps = cap.get(cv2.CAP_PROP_FPS)
        if not fps or fps <= 1.0:
            fps = 25.0
        return (skip + 1) / fps

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
            skip = config.LIVE_FRAME_SKIP if cam.get("live") else config.FRAME_SKIP
            # Pacing a velocidad real solo para video grabado: una cámara en
            # vivo ya se autorregula por el framerate con el que llega el
            # stream (cap.read() bloquea hasta el siguiente frame), un sleep
            # artificial encima solo le sumaría latencia.
            frame_interval = 0.0 if cam.get("live") else self._frame_interval(cap, skip)
            if not cap.isOpened():
                self._fail_open(cam)

            while not self._stop.is_set():
                loop_start = time.monotonic()
                requested = self._current_request()
                if requested != camera_key or cap is None or not cap.isOpened():
                    if cap is not None:
                        cap.release()
                    camera_key = requested
                    cap, cam = self._open_capture(camera_key)
                    skip = config.LIVE_FRAME_SKIP if cam.get("live") else config.FRAME_SKIP
                    frame_interval = 0.0 if cam.get("live") else self._frame_interval(cap, skip)
                    if not cap.isOpened():
                        self._fail_open(cam)
                        time.sleep(0.4)
                        continue

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

                annotated, vehicles, stationary, jam, queue_result = self._process_frame(frame, cam["key"])
                self._maybe_alert(jam, vehicles, stationary, cam["camera_id"])
                self._publish_frame(annotated, vehicles, stationary, jam, queue_result=queue_result)

                elapsed = time.monotonic() - loop_start
                remaining = frame_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
        except Exception as exc:  # noqa: BLE001 — el hilo no debe morir en silencio
            self._set_error(str(exc))
        finally:
            if cap is not None:
                cap.release()

    def _process_frame(
        self, frame: np.ndarray, camera_key: str
    ) -> tuple[np.ndarray, int, int, bool, QueueResult]:
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

        h, w = frame.shape[:2]
        # --- Hardcodeado (fase de pruebas): solo estas cámaras pasan por el
        # filtro espacial de zona + detección de cabeza de fila/cola. Cámara 1
        # y Cámara 2 siguen exactamente como antes (heurístico de movimiento
        # sobre el frame completo), sin importar si tienen un JSON de zonas
        # guardado. Agregar una cámara a config.CAMARAS_CON_FILTRO_ZONA basta
        # para habilitarle ambas cosas — no hay nada más que tocar aquí.
        apply_zone_filter = camera_key in config.CAMARAS_CON_FILTRO_ZONA
        cam_zones = load_zones(camera_key) if apply_zone_filter else None
        if cam_zones is not None:
            self._draw_zone_overlay(annotated, cam_zones, w, h)

        # Guardamos los datos de cada detección para dibujar en un segundo
        # pase, una vez que ya sabemos cuál es la cabeza de fila (solo se
        # conoce tras recorrer todos los vehículos detenidos del frame).
        render_items: list[dict[str, Any]] = []
        queue_candidates: list[tuple[int, tuple[float, float]]] = []

        boxes = result.boxes
        if boxes is not None and boxes.id is not None:
            xyxy = boxes.xyxy.cpu().numpy()
            ids = boxes.id.cpu().numpy().astype(int)
            for box, track_id in zip(xyxy, ids):
                x1, y1, x2, y2 = box

                # --- Filtro espacial: primera etapa, antes del heurístico
                # de movimiento. Un vehículo fuera del área de circulación
                # (banqueta, cajón de estacionamiento) queda excluido del
                # análisis de embotellamiento sin importar su historial.
                # Solo aplica si la cámara está en CAMARAS_CON_FILTRO_ZONA.
                bx, by = bottom_center(box)
                if apply_zone_filter and not cam_zones.contains(bx, by, w, h):
                    render_items.append({"excluded": True, "box": box})
                    continue

                cx = float((x1 + x2) / 2)
                cy = float((y1 + y2) / 2)
                seen.add(int(track_id))
                mem = self._tracks.get(int(track_id))
                if mem is None:
                    mem = TrackMemory(cx=cx, cy=cy, last_move_ts=now)
                    self._tracks[int(track_id)] = mem
                    idle_for_long = False
                else:
                    dist = hypot(cx - mem.cx, cy - mem.cy)
                    if dist > config.PIXEL_TOLERANCE:
                        mem.last_move_ts = now
                        mem.stationary = False
                    mem.cx, mem.cy = cx, cy
                    idle_for_long = (now - mem.last_move_ts) >= config.STATIONARY_SECONDS
                    mem.stationary = idle_for_long

                # "Detenido" vs "en movimiento" dentro de la zona de calle.
                # DEPRECADO: antes existía una tercera clase "parked"
                # (vehículo que nunca se vio moverse -> se asumía
                # estacionado, no embotellamiento) porque no había filtro
                # espacial que garantizara que solo se mira el carril. Ahora
                # que el polígono de calle ya excluye banquetas/cajones de
                # estacionamiento (ver zones.py y CAMARAS_CON_FILTRO_ZONA),
                # cualquier vehículo detenido *dentro* de la zona es, por
                # definición, tráfico detenido — no estacionamiento. El
                # heurístico de movimiento (idle_for_long, arriba) sigue
                # decidiendo detenido/en movimiento; ya no decide
                # estacionado/tráfico.
                stopped = idle_for_long
                if stopped:
                    stationary_ids.add(int(track_id))

                # --- Tercera etapa (solo cámaras con filtro): candidato a
                # cola = vehículo detenido, ya dentro de la zona de calle.
                if apply_zone_filter and stopped:
                    queue_candidates.append((int(track_id), (bx, by)))

                render_items.append(
                    {
                        "excluded": False,
                        "box": box,
                        "track_id": int(track_id),
                        "stopped": stopped,
                    }
                )

        for tid in list(self._tracks):
            if tid not in seen:
                del self._tracks[tid]

        queue_result = EMPTY_QUEUE
        if apply_zone_filter and queue_candidates and cam_zones.calibrated:
            polygon_px = self._first_polygon_px(cam_zones, w, h)
            if polygon_px is not None:
                gap_threshold_px = (config.QUEUE_GAP_PERCENT / 100.0) * float(np.hypot(w, h))
                queue_result = build_queue(queue_candidates, polygon_px, gap_threshold_px)

        head_id = queue_result.head.track_id if queue_result.head else None
        queue_member_ids = {v.track_id for v in queue_result.members}

        for item in render_items:
            if item["excluded"]:
                self._draw_excluded(annotated, item["box"])
                continue
            self._draw_vehicle(
                annotated,
                item["box"],
                item["track_id"],
                item["stopped"],
                is_head=(item["track_id"] == head_id),
                in_queue=(item["track_id"] in queue_member_ids and item["track_id"] != head_id),
            )

        vehicle_count = len(seen)
        stationary_count = len(stationary_ids)
        jam = stationary_count >= config.JAM_THRESHOLD
        self._draw_overlay(annotated, vehicle_count, stationary_count, jam, queue_result)
        return annotated, vehicle_count, stationary_count, jam, queue_result

    def _first_polygon_px(self, cam_zones: CameraZones, w: int, h: int) -> np.ndarray | None:
        """Polígono (en píxeles del frame actual) usado para derivar el eje
        del carril. Toma el primero configurado para la cámara — si en el
        futuro se necesitan colas por carril separadas, este es el único
        lugar que habría que extender a múltiples polígonos."""
        for zone in cam_zones.polygons_norm:
            raw = zone.get("polygon") or []
            if len(raw) >= 3:
                return np.array([[x * w, y * h] for x, y in raw], dtype=np.float64)
        return None

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
                    f"{stationary_count} vehículos detenidos "
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
        queue_result: QueueResult = EMPTY_QUEUE,
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
            self.state.queue_head_id = queue_result.head.track_id if queue_result.head else None
            self.state.queue_members = [v.track_id for v in queue_result.members]
            self.state.queue_length = queue_result.length_count
            self.state.queue_length_px = queue_result.length_px
            if clear_error:
                self.state.error = None

    def _set_error(self, message: str) -> None:
        with self.state.lock:
            self.state.error = message
        print(f"[SmartVia] {message}")

    def _draw_excluded(self, frame: np.ndarray, box: np.ndarray) -> None:
        """Vehículo fuera de la zona de circulación: se dibuja tenue solo
        para poder verificar la calibración, no entra al conteo/heurístico."""
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(frame, (x1, y1), (x2, y2), COLOR_EXCLUDED, 1)

    def _draw_zone_overlay(self, frame: np.ndarray, cam_zones: CameraZones, w: int, h: int) -> None:
        if not cam_zones.calibrated:
            return
        for zone in cam_zones.polygons_norm:
            raw = zone.get("polygon") or []
            if len(raw) < 3:
                continue
            pts = np.array([[int(x * w), int(y * h)] for x, y in raw], dtype=np.int32)
            cv2.polylines(frame, [pts], isClosed=True, color=COLOR_ZONE_OUTLINE, thickness=1)

    def _draw_vehicle(
        self,
        frame: np.ndarray,
        box: np.ndarray,
        track_id: int,
        stopped: bool,
        is_head: bool = False,
        in_queue: bool = False,
    ) -> None:
        # Nota: ya no existe una clase "parked" (P) — ver deprecación en
        # _process_frame. Dentro de la zona de calle solo hay tres estados:
        # M (en movimiento), D (detenido, tráfico), y las variantes de cola
        # H/Q para el vehículo detenido específico que origina el atasco.
        x1, y1, x2, y2 = map(int, box)
        thickness = 1
        if is_head:
            color = COLOR_QUEUE_HEAD
            tag = "H"
            thickness = 2
        elif in_queue:
            color = COLOR_QUEUE_MEMBER
            tag = "Q"
        elif stopped:
            color = COLOR_STOPPED
            tag = "D"
        else:
            color = COLOR_MOVING
            tag = "M"
        label = f"{track_id} {tag}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.35
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)
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

    def _draw_overlay(
        self, frame: np.ndarray, vehicles: int, stationary: int, jam: bool, queue_result: QueueResult = EMPTY_QUEUE
    ) -> None:
        _h, w = frame.shape[:2]
        status = "EMBOTELLAMIENTO" if jam else "TRAFICO FLUIDO"
        cam_label = self.state.camera_label
        text = f"{cam_label} | {status} | veh={vehicles} stop={stationary}"
        bar_h = 36
        if queue_result.head is not None:
            bar_h = 58
        cv2.rectangle(frame, (0, 0), (w, bar_h), COLOR_OVERLAY, -1)
        cv2.putText(
            frame,
            text,
            (12, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            COLOR_STOPPED if jam else COLOR_MOVING,
            2,
            cv2.LINE_AA,
        )
        if queue_result.head is not None:
            queue_text = (
                f"Cola: cabeza=#{queue_result.head.track_id} · "
                f"{queue_result.length_count} vehiculos · ~{int(queue_result.length_px)}px"
            )
            cv2.putText(
                frame,
                queue_text,
                (12, 48),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                COLOR_QUEUE_HEAD,
                1,
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
