from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

from src.modules.bms.application.queries.get_status_handler import GetBmsStatusQuery, GetBmsStatusHandler
from src.modules.bms.application.queries.get_history_handler import GetBmsHistoryQuery, GetBmsHistoryHandler

def create_app(repository):
    app = Flask(__name__)
    CORS(app)
    sock = Sock(app)
    
    status_handler = GetBmsStatusHandler(repository)
    history_handler = GetBmsHistoryHandler(repository)
    
    _clients = set()

    @app.route("/api/status")
    async def get_status():
        reading = await status_handler.execute(GetBmsStatusQuery())
        if not reading: return jsonify({"connected": False, "data": None})
        return jsonify({"connected": True, "data": reading.to_dict()})

    @app.route("/api/history/<metric>")
    async def get_history(metric):
        limit = request.args.get("limit", default=200, type=int)
        points = await history_handler.execute(GetBmsHistoryQuery(metric, limit))
        return jsonify({"metric": metric, "points": points})

    @sock.route("/ws")
    def ws_endpoint(ws):
        _clients.add(ws)
        try:
            while True: ws.receive()
        except Exception: pass
        finally: _clients.discard(ws)

    return app
