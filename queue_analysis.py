"""Detección de cabeza de fila y agrupamiento de cola de embotellamiento.

Módulo genérico y reutilizable: no hay nada específico de una cámara en
particular aquí. Cualquier cámara que entre a `config.CAMARAS_CON_FILTRO_ZONA`
puede usar `build_queue()` sin duplicar lógica — solo necesita, para cada
frame, la lista de vehículos "detenidos" (ya filtrados por zona) con su
punto bottom-center, y el polígono de carril (en píxeles del frame actual)
para derivar el eje de circulación.

Eje de circulación: se calcula por PCA sobre los vértices del polígono de
la zona de calle (su eje más largo = dirección del carril). No se hardcodea
"eje X" o "eje Y" para que la misma función sirva sin cambios en cámaras
con encuadres distintos. La orientación "hacia adelante" usa como
heurística que la cola se acumula hacia la cámara (parte baja del frame) y
el carril avanza hacia arriba de la imagen — válido para el encuadre típico
de cámara de tráfico elevada. Si una cámara futura no cumple esa heurística,
puede ajustarse aquí sin tocar el resto del pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class QueueVehicle:
    track_id: int
    point: tuple[float, float]  # bottom-center, píxeles del frame actual
    progress: float             # proyección escalar sobre el eje del carril (mayor = más adelantado)


@dataclass
class QueueResult:
    head: QueueVehicle | None
    members: list[QueueVehicle]  # cabeza incluida, ordenados cabeza -> cola
    length_count: int
    length_px: float

    def to_dict(self) -> dict:
        return {
            "head_track_id": self.head.track_id if self.head else None,
            "head_point": list(self.head.point) if self.head else None,
            "members": [
                {"track_id": v.track_id, "point": list(v.point)} for v in self.members
            ],
            "length_count": self.length_count,
            "length_px": round(self.length_px, 1),
        }


EMPTY_QUEUE = QueueResult(head=None, members=[], length_count=0, length_px=0.0)


def lane_axis_for_polygon(polygon_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Eje principal (dirección del carril) del polígono vía PCA + su centroide.
    Devuelve un vector unitario que apunta "hacia adelante" (ver docstring
    del módulo sobre la heurística de orientación)."""
    centroid = polygon_px.mean(axis=0)
    centered = polygon_px - centroid
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    axis = eigvecs[:, int(np.argmax(eigvals))]
    norm = np.linalg.norm(axis)
    if norm > 1e-9:
        axis = axis / norm
    if axis[1] > 0:  # "adelante" = hacia arriba de la imagen (menor y)
        axis = -axis
    return axis, centroid


def build_queue(
    stopped_vehicles: list[tuple[int, tuple[float, float]]],
    polygon_px: np.ndarray,
    gap_threshold_px: float,
) -> QueueResult:
    """A partir de vehículos ya detenidos y ya filtrados por zona, encuentra
    la cabeza de fila (el más adelantado) y agrupa hacia atrás mientras la
    separación entre vehículos consecutivos no supere `gap_threshold_px`.
    Un vehículo detenido "suelto" (separado por más del umbral) no entra
    a la cola, aunque esté dentro de la misma zona."""
    if not stopped_vehicles or len(polygon_px) < 3:
        return EMPTY_QUEUE

    axis, centroid = lane_axis_for_polygon(polygon_px)
    scored = [
        QueueVehicle(
            track_id=tid,
            point=pt,
            progress=float(np.dot(np.array(pt, dtype=np.float64) - centroid, axis)),
        )
        for tid, pt in stopped_vehicles
    ]
    scored.sort(key=lambda v: v.progress, reverse=True)  # cabeza = más adelantado

    members = [scored[0]]
    for vehicle in scored[1:]:
        gap = members[-1].progress - vehicle.progress
        if gap <= gap_threshold_px:
            members.append(vehicle)
        else:
            break  # vehículo suelto: rompe la continuidad de la cola

    length_px = members[0].progress - members[-1].progress if len(members) > 1 else 0.0
    return QueueResult(head=members[0], members=members, length_count=len(members), length_px=length_px)
