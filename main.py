import threading
import asyncio
from src.modules.shared.infrastructure.config.config import config
from src.modules.bms.infrastructure.adapters.bleak_bms_repository import BleakBmsRepository
from src.modules.bms.infrastructure.entrypoints.flask_app import create_app

def main():
    repository = BleakBmsRepository()

    def run_ble():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(repository.start_polling())

    ble_thread = threading.Thread(target=run_ble, daemon=True)
    ble_thread.start()

    app = create_app(repository)
    print(f"BMS Monitor [Modulo BMS] iniciado en puerto {config.FLASK_PORT}")
    app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.FLASK_DEBUG, threaded=True)

if __name__ == "__main__":
    main()
