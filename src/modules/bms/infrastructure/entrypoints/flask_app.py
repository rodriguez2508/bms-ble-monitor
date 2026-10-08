import asyncio
import json
import os

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

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

WS_PUSH_INTERVAL = 2  # seconds between server-pushed status frames


def create_app(repository):
    app = Flask(__name__)
    CORS(app)
    sock = Sock(app)

    status_handler = GetBmsStatusHandler(repository)
    history_handler = GetBmsHistoryHandler(repository)
    config_handler = GetBmsConfigHandler(repository)
    balance_handler = GetBalanceLogHandler(repository)

    _clients = set()

    @app.route("/")
    @app.route("/dashboard")
    def dashboard():
        return send_from_directory(
            STATIC_DIR, "index.html", mimetype="text/html"
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
                }
                ws.send(json.dumps(payload))
        except Exception:
            pass
        finally:
            _clients.discard(ws)

    return app
