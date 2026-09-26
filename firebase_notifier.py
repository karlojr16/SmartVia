"""Alertas hacia el panel PECUU y mock FCM.

El dashboard de policía (Next.js) espera POST JSON en PECUU_ALERTS_URL
con al menos: camera_id, vehicle_count, timestamp, severity.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

import config

# ---------------------------------------------------------------------------
# Inyección de credenciales FCM (descomentar cuando tengas serviceAccountKey.json)
# ---------------------------------------------------------------------------
# import firebase_admin
# from firebase_admin import credentials, messaging
#
# _CREDENTIALS_PATH = "serviceAccountKey.json"
# if not firebase_admin._apps:
#     cred = credentials.Certificate(_CREDENTIALS_PATH)
#     firebase_admin.initialize_app(cred)
#
# FCM_TOPIC = "smartvia-alerts"


def send_jam_alert(payload: dict[str, Any]) -> None:
    """Envía la alerta al Command Center PECUU y deja el mock FCM en consola."""
    detected_at = payload.get("detected_at") or datetime.now(timezone.utc).isoformat()
    pecuu_body = {
        "camera_id": payload.get("camera_id", config.CAMERA_ID),
        "vehicle_count": int(payload.get("vehicle_count", 0)),
        "stationary_count": int(payload.get("stationary_count", 0)),
        "timestamp": detected_at,
        "severity": payload.get(
            "severity",
            "CRITICAL — possible jam / collision",
        ),
        "event": "jam",
        "title": payload.get("title", "SmartVia: embotellamiento"),
        "body": payload.get("body", "Se detectó tráfico detenido."),
    }
    _post_pecuu(pecuu_body)

    fcm_body = {
        "notification": {
            "title": pecuu_body["title"],
            "body": pecuu_body["body"],
        },
        "data": {
            "event": "jam",
            "camera_id": str(pecuu_body["camera_id"]),
            "vehicle_count": str(pecuu_body["vehicle_count"]),
            "stationary_count": str(pecuu_body["stationary_count"]),
            "detected_at": detected_at,
        },
    }
    print("[FCM MOCK] payload:")
    print(json.dumps(fcm_body, indent=2, ensure_ascii=False))

    # Envío FCM real (descomentar con credenciales):
    # message = messaging.Message(
    #     notification=messaging.Notification(
    #         title=fcm_body["notification"]["title"],
    #         body=fcm_body["notification"]["body"],
    #     ),
    #     data=fcm_body["data"],
    #     topic=FCM_TOPIC,
    # )
    # messaging.send(message)


def _post_pecuu(body: dict[str, Any]) -> None:
    data = json.dumps(body).encode("utf-8")
    req = Request(
        config.PECUU_ALERTS_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=15) as resp:
            print(f"[PECUU] alerta enviada ({resp.status}): {body.get('camera_id')}")
    except URLError as exc:
        print(f"[PECUU] no se pudo enviar la alerta a {config.PECUU_ALERTS_URL}: {exc}")
    except Exception as exc:  # noqa: BLE001
        print(f"[PECUU] error inesperado al enviar alerta: {exc}")
