"""Filtro espacial: zonas de circulación (carril/calle) por cámara.

Antes de aplicar el heurístico de movimiento (parado vs. en movimiento),
cada vehículo se filtra por posición: solo los que caen dentro del área
de circulación calibrada para su cámara entran al análisis de
embotellamiento. Los que están fuera (banqueta, cajones de
estacionamiento, etc.) se descartan sin importar si se movieron o no.

Las zonas se calibran en /calibrate/<camera_key> (UI web) y se guardan
como polígonos normalizados (0-1 respecto al frame) en zones/<camera_key>.json.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np

import config

logger = logging.getLogger("smartvia.zones")

ZONES_DIR = config.BASE_DIR / "zones"

# Comportamiento cuando una cámara todavía no tiene zonas calibradas:
#   "all"  -> analizar todo el frame (compatible con el comportamiento previo)
#   "none" -> no analizar ningún vehículo hasta que se calibre la cámara
DEFAULT_UNCALIBRATED_MODE = getattr(config, "ZONE_DEFAULT_MODE", "all")

DEFAULT_BUFFER_PERCENT = 1.5


class CameraZones:
    """Zonas de circulación ya cargadas para una cámara."""

    def __init__(self, camera_key: str, polygons_norm: list[dict[str, Any]], buffer_percent: float):
        self.camera_key = camera_key
        self.polygons_norm = polygons_norm
        self.buffer_percent = buffer_percent
        self.calibrated = bool(polygons_norm)

    def contains(self, px: float, py: float, frame_w: int, frame_h: int) -> bool:
        """¿El punto (px, py), en píxeles del frame ya procesado, cae dentro
        de alguna zona de circulación (con tolerancia de buffer)?"""
        if not self.calibrated:
            return DEFAULT_UNCALIBRATED_MODE == "all"

        buffer_px = (self.buffer_percent / 100.0) * float(np.hypot(frame_w, frame_h))
        for zone in self.polygons_norm:
            raw = zone.get("polygon") or []
            if len(raw) < 3:
                continue
            pts = np.array([[x * frame_w, y * frame_h] for x, y in raw], dtype=np.float32)
            # measureDist=True -> distancia con signo (+ dentro, - fuera).
            dist = cv2.pointPolygonTest(pts, (float(px), float(py)), True)
            if dist >= -buffer_px:
                return True
        return False


_cache: dict[str, CameraZones] = {}


def _path_for(camera_key: str) -> Path:
    return ZONES_DIR / f"{camera_key}.json"


def load_zones(camera_key: str) -> CameraZones:
    """Carga (con caché) las zonas de una cámara. Loggea advertencia
    explícita si la cámara no tiene calibración todavía."""
    cached = _cache.get(camera_key)
    if cached is not None:
        return cached

    path = _path_for(camera_key)
    if not path.exists():
        logger.warning(
            "Cámara '%s' sin zona de circulación calibrada (%s). "
            "Modo por defecto: '%s'. Calibra en /calibrate/%s.",
            camera_key, path, DEFAULT_UNCALIBRATED_MODE, camera_key,
        )
        zones = CameraZones(camera_key, [], DEFAULT_BUFFER_PERCENT)
        _cache[camera_key] = zones
        return zones

    try:
        data = json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo leer zonas de '%s' (%s): %s. Usando modo por defecto.", camera_key, path, exc)
        zones = CameraZones(camera_key, [], DEFAULT_BUFFER_PERCENT)
        _cache[camera_key] = zones
        return zones

    polygons = [z for z in data.get("zones", []) if len(z.get("polygon") or []) >= 3]
    buffer_percent = float(data.get("buffer_percent", DEFAULT_BUFFER_PERCENT))
    if not polygons:
        logger.warning(
            "Cámara '%s' tiene %s pero sin polígonos válidos. Modo por defecto: '%s'.",
            camera_key, path, DEFAULT_UNCALIBRATED_MODE,
        )
    zones = CameraZones(camera_key, polygons, buffer_percent)
    _cache[camera_key] = zones
    return zones


def invalidate(camera_key: str) -> None:
    """Fuerza recarga de zonas en el próximo load_zones (tras recalibrar)."""
    _cache.pop(camera_key, None)


def bottom_center(box: np.ndarray) -> tuple[float, float]:
    """Punto de referencia del bbox para el filtro espacial: el
    bottom-center, que se acerca más al punto de contacto con el suelo
    y compensa mejor la perspectiva de la cámara que el centro completo."""
    x1, y1, x2, y2 = box
    return float((x1 + x2) / 2.0), float(y2)


def read_raw(camera_key: str) -> dict[str, Any]:
    """Config cruda de zonas para servir/editar en la UI de calibración."""
    path = _path_for(camera_key)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"camera_id": camera_key, "zones": [], "buffer_percent": DEFAULT_BUFFER_PERCENT}


def save_zones(camera_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Valida y guarda las zonas de una cámara, normalizando coordenadas
    a [0, 1] y descartando polígonos degenerados (<3 vértices)."""
    cleaned: list[dict[str, Any]] = []
    for idx, zone in enumerate(payload.get("zones", [])):
        name = str(zone.get("name") or f"zona_{idx + 1}").strip() or f"zona_{idx + 1}"
        pts: list[list[float]] = []
        for pt in zone.get("polygon", []):
            x = min(max(float(pt[0]), 0.0), 1.0)
            y = min(max(float(pt[1]), 0.0), 1.0)
            pts.append([x, y])
        if len(pts) >= 3:
            cleaned.append({"name": name, "polygon": pts})

    buffer_percent = float(payload.get("buffer_percent", DEFAULT_BUFFER_PERCENT))
    data = {
        "camera_id": camera_key,
        "frame_width": payload.get("frame_width"),
        "frame_height": payload.get("frame_height"),
        "buffer_percent": buffer_percent,
        "zones": cleaned,
    }
    ZONES_DIR.mkdir(parents=True, exist_ok=True)
    _path_for(camera_key).write_text(json.dumps(data, indent=2, ensure_ascii=False))
    invalidate(camera_key)
    return data
