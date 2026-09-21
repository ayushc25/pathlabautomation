"""Windows service entrypoint for the lab decoder application."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from pathlib import Path

import uvicorn

from app.main import app
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _base_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def run_server() -> None:
    host = os.getenv("LAB_APP_HOST", "0.0.0.0")
    port = int(os.getenv("LAB_APP_PORT", "8000"))
    try:
        uvicorn.run(app, host=host, port=port, log_level="info")
    except SystemExit as exc:
        # uvicorn.run() raises SystemExit (not Exception) when FastAPI's startup
        # fails - and Python's threading module silently discards SystemExit
        # from a background thread, so without this the failure leaves no trace
        # at all. The real cause was already logged by uvicorn just above this.
        logger.error("uvicorn exited during startup (code=%s) - see the traceback logged just above for the real cause", exc.code)
        return
    except Exception:
        logger.exception("uvicorn.run() raised - server thread exiting")
        raise
    logger.error(
        "uvicorn.run() returned without an exception - this almost always means "
        "app startup failed (e.g. a startup event raised, or the port is already "
        "in use). The service will now stop; check the log lines above for the cause."
    )


def open_browser() -> None:
    url = os.getenv("LAB_APP_URL", "http://127.0.0.1:8000")
    time.sleep(2)
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:
        pass


def main() -> None:
    from app.services.license import LicenseError, ensure_licensed

    try:
        ensure_licensed()
    except LicenseError as exc:
        logger.error("License check failed - service will not start: %s", exc)
        raise

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    open_browser()
    server_thread.join()
    logger.error("Server thread ended - main() is returning, service will report as stopped.")


if __name__ == "__main__":
    main()
