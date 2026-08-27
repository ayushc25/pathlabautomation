"""FastAPI application entry point for the HORIBA Yumizen H500/H500E
ASTM decoder service."""
from __future__ import annotations

from pathlib import Path

import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
import threading
import time

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.utils.logger import get_logger

_logger = get_logger(__name__)
_DEFAULT_SESSION_SECRET = "dummy-login-secret-key"
SESSION_SECRET_KEY = os.environ.get("SESSION_SECRET_KEY", _DEFAULT_SESSION_SECRET)
if SESSION_SECRET_KEY == _DEFAULT_SESSION_SECRET:
    _logger.warning(
        "SESSION_SECRET_KEY is not set; using an insecure default. "
        "Set SESSION_SECRET_KEY in the environment before deploying to production."
    )

from app.routers import decode
from app.routers import results
from app.routers import ui
from app.routers import piysan
from app.services.database import init_databases
from app.services.socket_listener import AnalyzerListener

app = FastAPI(
    title="HORIBA Yumizen H500/H500E ASTM Decoder",
    description=(
        "Decodes raw ASTM host-connection captures from HORIBA Yumizen "
        "H500/H500E hematology analyzers (per the RAA085BEN spec) into "
        "structured patient, order, result, comment, histogram and matrix data."
    ),
    version="1.0.0",
)

app.include_router(decode.router)
app.include_router(results.router)
app.include_router(ui.router)
app.include_router(piysan.router)

SESSION_IDLE_TIMEOUT_SECONDS = 60 * 60  # auto-logout after 1 hour of inactivity


class IdleSessionTimeoutMiddleware(BaseHTTPMiddleware):
    """Clears the session (forcing a re-login) once it has been idle past the timeout."""

    async def dispatch(self, request: Request, call_next):
        session = request.session
        if session.get("authenticated"):
            now = time.time()
            last_activity = session.get("last_activity")
            if last_activity is not None and (now - last_activity) > SESSION_IDLE_TIMEOUT_SECONDS:
                session.clear()
            else:
                session["last_activity"] = now
        return await call_next(request)


# NOTE: order matters - the middleware added LAST runs FIRST on the way in, so
# SessionMiddleware (which decodes the session cookie into request.session) must
# be added after IdleSessionTimeoutMiddleware so the session is already populated
# by the time our idle check runs.
app.add_middleware(IdleSessionTimeoutMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET_KEY, same_site="lax")
listener = AnalyzerListener()
_watchdog_stop = threading.Event()


def _listener_watchdog() -> None:
    while not _watchdog_stop.is_set():
        time.sleep(10)
        if not listener.is_running():
            try:
                listener.ensure_running()
            except Exception:
                pass


@app.on_event("startup")
async def startup_event() -> None:
    init_databases()
    listener.start()
    app.state.listener = listener
    if not hasattr(app.state, "watchdog_thread") or not app.state.watchdog_thread.is_alive():
        _watchdog_stop.clear()
        app.state.watchdog_thread = threading.Thread(target=_listener_watchdog, daemon=True, name="ListenerWatchdog")
        app.state.watchdog_thread.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    _watchdog_stop.set()
    listener.stop()


@app.get("/health", tags=["meta"])
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok", "listener_running": listener.is_running()})
