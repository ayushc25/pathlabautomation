"""Test Results screen: browse raw captures for the selected machine and
decode them individually into structured JSON."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services import astm_parser, report_generator
from app.services.database import (
    load_machines,
    load_raw_capture,
    load_raw_captures,
    load_users,
    upsert_machine,
    upsert_user,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["results"])
BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

DEMO_USER = "admin"
LAB_DISPLAY_NAME = "Sk lab"
DEFAULT_MACHINE_NAMES = [
    "HORIBA Yumizen H500",
    "Machine 1 (dummy)",
    "Machine 2 (dummy)",
    "Machine 3 (dummy)",
]
RAW_CAPTURE_LIMIT = 100


def _authed(request: Request) -> bool:
    return bool(request.session.get("authenticated"))


def _packet_identifiers(payload: str) -> Dict[str, Any]:
    """Pull the order number and patient ID straight out of the raw packet
    (its O/P records) - not anything stored in the database - so the list
    always reflects what the analyzer actually sent."""
    try:
        parsed = astm_parser.parse_capture(payload)
    except Exception:  # noqa: BLE001 - preview only, never blocks the listing
        return {"order_number": None, "patient_id": None}
    return {
        "order_number": parsed.order.get("sample_id"),
        "patient_id": parsed.patient.get("patient_id"),
    }


def _ensure_user_and_machines():
    users = load_users()
    if not users:
        user_id = upsert_user(LAB_DISPLAY_NAME)
        users = [{"id": user_id, "user_name": LAB_DISPLAY_NAME}]
    user = users[0]
    machines = load_machines(user["id"])
    if not machines:
        machines = []
        for machine_name in DEFAULT_MACHINE_NAMES:
            machine_id = upsert_machine(user["id"], machine_name)
            machines.append({"id": machine_id, "machine_name": machine_name})
    return user, machines


@router.get("/test-results", response_class=HTMLResponse, include_in_schema=False)
async def test_results_page(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    user, machines = _ensure_user_and_machines()
    requested_machine_id = request.query_params.get("machine_id")
    machine = next((m for m in machines if str(m["id"]) == str(requested_machine_id)), machines[0])

    raw_captures = load_raw_captures(limit=RAW_CAPTURE_LIMIT)
    for capture in raw_captures:
        capture.update(_packet_identifiers(capture["payload"]))

    return templates.TemplateResponse(
        request=request,
        name="test_results.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "customer_name": LAB_DISPLAY_NAME,
            "machines": machines,
            "active_machine": machine,
            "raw_captures": raw_captures,
        },
    )


@router.post("/test-results/select-machine", include_in_schema=False)
async def select_machine(request: Request):
    form = await request.form()
    machine_id = form.get("machine_id")
    return RedirectResponse(f"/test-results?machine_id={machine_id}", status_code=302)


@router.post("/test-results/decode/{raw_capture_id}")
async def decode_raw_capture(raw_capture_id: int, request: Request) -> JSONResponse:
    if not _authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    capture = load_raw_capture(raw_capture_id)
    if not capture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw capture not found")

    try:
        report = report_generator.generate_report(
            capture["payload"],
            source="ui",
            raw_capture_id=raw_capture_id,
        )
    except astm_parser.ASTMParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected failure decoding raw capture %s", raw_capture_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while decoding capture: {exc}",
        ) from exc

    return JSONResponse({
        "raw_capture_id": raw_capture_id,
        "order_number": report.get("order", {}).get("sample_id"),
        "patient_id": report.get("patient", {}).get("patient_id"),
        "report": report,
    })
