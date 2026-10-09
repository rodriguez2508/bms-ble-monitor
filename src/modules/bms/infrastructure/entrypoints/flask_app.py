import asyncio
import json
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_sock import Sock

from src.modules.bms.application.queries.get_status_handler import (
    GetBmsStatusQuery,
    GetBmsStatusHandler,
)
from src.modules.bms.application.queries.get_history_handler import (
    GetBmsHistoryQuery,
    GetBmsHistoryHandler,
)
from src.modules.bms.application.queries.get_config_handler import (
    GetBmsConfigQuery,
    GetBmsConfigHandler,
)
from src.modules.bms.application.queries.get_balance_log_handler import (
    GetBalanceLogQuery,
    GetBalanceLogHandler,
)
from src.modules.bms.application.services.soc_alert import SocAlertService
from src.modules.bms.infrastructure.adapters.push_service import PushService
from src.modules.shared.infrastructure.config.config import config

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

WS_PUSH_INTERVAL = 2  # seconds between server-pushed status frames
STATIC_WATCH_INTERVAL = 1  # seconds between static-file change checks (dev)


def _static_signature() -> str:
    # Cheap fingerprint of the served static files (path + mtime).
    parts = []
    for root, _dirs, files in os.walk(STATIC_DIR):
        for name in sorted(files):
            path = os.path.join(root, name)
            try:
                parts.append(f"{path}:{os.path.getmtime(path)}")
            except OSError:
                pass
    return "|".join(parts)


def _build_push_service() -> PushService:
    data_dir = config.DATA_DIR
    return PushService(
        os.path.join(data_dir, config.VAPID_KEYS_FILE),
        os.path.join(data_dir, config.PUSH_SUBSCRIBE_FILE),
        config.VAPID_SUBJECT,
    )


def _build_soc_alert(push_service: PushService) -> SocAlertService:
    return SocAlertService(
        push_service,
        os.path.join(config.DATA_DIR, config.ALERT_CONFIG_FILE),
        config.SOC_ALERT_PCT,
        config.SOC_ALERT_HYSTERESIS,
        config.SOC_HIGH_ALERT_PCT,
        config.SOC_HIGH_HYSTERESIS,
    )


def create_app(repository, push_service=None, soc_alert=None, start_watcher=True):
    app = Flask(__name__)
    CORS(app)
    sock = Sock(app)

    status_handler = GetBmsStatusHandler(repository)
    history_handler = GetBmsHistoryHandler(repository)
    config_handler = GetBmsConfigHandler(repository)
    balance_handler = GetBalanceLogHandler(repository)

    push_service = push_service or _build_push_service()
    soc_alert = soc_alert or _build_soc_alert(push_service)

    _clients = set()
    static_state = {"version": 0}

    def _watch_alerts():
        # Independent of any open dashboard tab: reads the latest reading and
        # fires a push when the SOC crosses the threshold.
        if config.PUSH_ON_START:
            try:
                push_service.send("BMS Monitor", "Servidor iniciado")
            except Exception:
                pass
        while True:
            try:
                reading = asyncio.run(status_handler.execute(GetBmsStatusQuery()))
                if reading is not None:
                    age = (datetime.now() - reading.timestamp).total_seconds()
                    if age <= config.ALERT_STALE_SECONDS:
                        soc_alert.evaluate(reading)
            except Exception:
                pass
            time.sleep(config.ALERT_CHECK_INTERVAL)

    def _watch_static():
        # Dev live-reload: bump a counter when the served static files change;
        # the WS loop forwards it so open dashboards reload themselves.
        last = _static_signature()
        while True:
            time.sleep(STATIC_WATCH_INTERVAL)
            signature = _static_signature()
            if signature != last:
                last = signature
                static_state["version"] += 1

    # Skip under the Werkzeug reloader's parent process to avoid double workers.
    reloader_active = config.FLASK_DEBUG or config.FLASK_RELOAD
    in_serving_process = (
        os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not reloader_active
    )
    if start_watcher and in_serving_process:
        threading.Thread(target=_watch_alerts, name="alert-watch", daemon=True).start()
    if reloader_active and in_serving_process:
        threading.Thread(target=_watch_static, name="static-watch", daemon=True).start()

    @app.route("/")
    @app.route("/dashboard")
    def dashboard():
        return send_from_directory(
            STATIC_DIR, "index.html", mimetype="text/html"
        )

    @app.route("/sw.js")
    def service_worker():
        # Must be served from the origin root so its scope covers "/".
        return send_from_directory(
            STATIC_DIR, "sw.js", mimetype="application/javascript"
        )

    @app.route("/app.js")
    def app_js():
        # External script: allowed under a 'self' CSP (inline scripts are not).
        return send_from_directory(
            STATIC_DIR, "app.js", mimetype="application/javascript"
        )

    @app.route("/api/status")
    async def get_status():
        reading = await status_handler.execute(GetBmsStatusQuery())
        if not reading:
            return jsonify({"connected": False, "data": None})
        return jsonify({"connected": True, "data": reading.to_dict()})

    @app.route("/api/config")
    async def get_config():
        cfg = await config_handler.execute(GetBmsConfigQuery())
        if not cfg:
            return jsonify({"connected": False, "data": None})
        return jsonify({"connected": True, "data": cfg.to_dict()})

    @app.route("/api/history/<metric>")
    async def get_history(metric):
        limit = request.args.get("limit", default=200, type=int)
        points = await history_handler.execute(
            GetBmsHistoryQuery(metric, limit)
        )
        return jsonify({"metric": metric, "points": points})

    @app.route("/api/balance")
    async def get_balance():
        limit = request.args.get("limit", default=200, type=int)
        points = await balance_handler.execute(GetBalanceLogQuery(limit))
        return jsonify({"points": points})

    @app.route("/api/push/public_key")
    def push_public_key():
        return jsonify({"key": push_service.public_key})

    @app.route("/api/push/subscribe", methods=["POST"])
    def push_subscribe():
        subscription = request.get_json(silent=True) or {}
        return jsonify({"ok": push_service.subscribe(subscription)})

    @app.route("/api/push/unsubscribe", methods=["POST"])
    def push_unsubscribe():
        body = request.get_json(silent=True) or {}
        endpoint = body.get("endpoint", "")
        if endpoint:
            push_service.unsubscribe(endpoint)
        return jsonify({"ok": True})

    @app.route("/api/push/test", methods=["POST"])
    def push_test():
        sent = push_service.send("Batería BMS", "Notificación de prueba del dashboard.")
        return jsonify({"ok": True, "sent": sent})

    @app.route("/api/alerts/config", methods=["GET", "POST"])
    def alerts_config():
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            low = body.get("soc_alert_pct")
            high = body.get("soc_high_alert_pct")
            if low is None and high is None:
                return jsonify(
                    {"ok": False, "error": "falta soc_alert_pct o soc_high_alert_pct"}
                ), 400
            try:
                if low is not None:
                    soc_alert.set_threshold(float(low))
                if high is not None:
                    soc_alert.set_high_threshold(float(high))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "valor invalido"}), 400
            return jsonify({"ok": True, **soc_alert.status()})
        return jsonify(soc_alert.status())

    @sock.route("/ws")
    def ws_endpoint(ws):
        # Each WS handler runs in its own thread; push on the handler's own
        # socket (never from another thread) after a short receive timeout.
        _clients.add(ws)
        try:
            while True:
                try:
                    ws.receive(timeout=WS_PUSH_INTERVAL)
                except Exception:
                    break  # client disconnected
                # get_latest_reading only takes a threading.Lock and never
                # touches the BLE event loop, so it is safe to call here.
                reading = asyncio.run(
                    status_handler.execute(GetBmsStatusQuery())
                )
                payload = {
                    "type": "status",
                    "connected": reading is not None,
                    "data": reading.to_dict() if reading else None,
                    "static_version": static_state["version"],
                }
                ws.send(json.dumps(payload))
        except Exception:
            pass
        finally:
            _clients.discard(ws)

    return app
