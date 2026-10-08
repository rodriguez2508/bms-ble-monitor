import asyncio
import signal
import threading

from src.modules.shared.infrastructure.config.config import config
from src.modules.bms.infrastructure.adapters.bleak_bms_repository import BleakBmsRepository
from src.modules.bms.infrastructure.entrypoints.flask_app import create_app


def main():
    repository = BleakBmsRepository()
    ble_loop = asyncio.new_event_loop()
    state: dict = {}
    stopped = threading.Event()

    def run_ble():
        asyncio.set_event_loop(ble_loop)
        task = ble_loop.create_task(repository.start_polling())
        state["task"] = task
        try:
            ble_loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        finally:
            # Safety net: if cancellation interrupted cleanup, make sure the BLE
            # link is released so the BMS advertises again for the next start.
            try:
                ble_loop.run_until_complete(repository.disconnect())
            except Exception as e:
                print(f"[BLE] Error en shutdown: {type(e).__name__}: {e!r}")
            ble_loop.close()

    ble_thread = threading.Thread(target=run_ble, name="ble", daemon=True)
    ble_thread.start()

    def shutdown(*_args):
        # Stop the polling loop and disconnect cleanly before the process exits.
        if stopped.is_set():
            return
        stopped.set()

        def _stop():
            repository.request_stop()
            task = state.get("task")
            if task is not None and not task.done():
                task.cancel()

        try:
            ble_loop.call_soon_threadsafe(_stop)
        except RuntimeError:
            pass  # loop already closed
        ble_thread.join(timeout=15)

    def _on_sigterm(*_args):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, _on_sigterm)

    app = create_app(repository)
    print(f"BMS Monitor [Modulo BMS] iniciado en puerto {config.FLASK_PORT}")
    try:
        app.run(host="0.0.0.0", port=config.FLASK_PORT, debug=config.FLASK_DEBUG, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()


if __name__ == "__main__":
    main()
