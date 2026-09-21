"""FastAPI Router for Piysan LIS integration endpoints."""
from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.services.piysan_service import (
    execute_piysan_request,
    get_piysan_base_url,
    get_piysan_settings,
    load_enriched_bookings,
    load_submission_logs,
    manual_submit_to_piysan,
    save_piysan_bookings,
    toggle_skip_booking,
    update_piysan_settings,
)

router = APIRouter(tags=["piysan"])
BASE_DIR = Path(__file__).resolve().parents[2]
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

DEMO_USER = "admin"


def _authed(request: Request) -> bool:
    """Check session authentication status."""
    return bool(request.session.get("authenticated"))


@router.get("/piysan", response_class=HTMLResponse, include_in_schema=False)
async def piysan_page(request: Request):
    """Render the Piysan LIS Management Dashboard page."""
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    settings = get_piysan_settings()
    bookings = load_enriched_bookings()
    logs = load_submission_logs(limit=50)

    return templates.TemplateResponse(
        request=request,
        name="piysan.html",
        context={
            "request": request,
            "username": request.session.get("username", DEMO_USER),
            "settings": settings,
            "active_base_url": get_piysan_base_url(),
            "bookings": bookings,
            "logs": logs,
            "saved": request.query_params.get("saved") == "1",
            "sync": request.query_params.get("sync") == "1",
            "error": request.query_params.get("error"),
        },
    )


@router.post("/piysan/settings", include_in_schema=False)
async def save_settings(
    request: Request,
    mobile: str = Form(...),
    password: str = Form(...),
    auto_submit: Optional[str] = Form(None),
):
    """Save Piysan LIS integration parameters. base_url comes from PIYSAN_BASE_URL env var, not this form."""
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    is_auto = 1 if auto_submit == "on" else 0
    update_piysan_settings(mobile, password, is_auto)
    return RedirectResponse("/piysan?saved=1", status_code=302)


@router.post("/piysan/test-connection")
async def test_connection(request: Request):
    """Test credentials connection by making a Login API call."""
    if not _authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    try:
        # execute_piysan_request("login") runs login() method on client
        # but wait, execute_piysan_request expects the method name, and inside it fetches settings
        # and executes the method. Since 'login' takes no arguments (except self), this is correct.
        token = execute_piysan_request("login")
        return JSONResponse({"status": "success", "message": "Successfully authenticated with Piysan LIS!"})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Connection test failed: {e}"},
            status_code=400,
        )


@router.post("/piysan/fetch-bookings", include_in_schema=False)
async def fetch_bookings(request: Request, next_page: str = Form("/dashboard")):
    """Sync booking assignments from Piysan LIS API."""
    if not _authed(request):
        return RedirectResponse("/login", status_code=302)

    if next_page not in ("/piysan", "/push-command", "/dashboard"):
        next_page = "/dashboard"

    try:
        bookings = execute_piysan_request("get_bookings", limit=200)
        save_piysan_bookings(bookings)
        return RedirectResponse(f"{next_page}?sync=1", status_code=302)
    except Exception as e:
        err_msg = urllib.parse.quote(str(e))
        return RedirectResponse(f"{next_page}?error={err_msg}", status_code=302)


@router.post("/piysan/submit/{reference_no}")
async def manual_submit_booking(reference_no: str, request: Request):
    """Manually push decoded ASTM laboratory results matching reference_no."""
    if not _authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    try:
        response = manual_submit_to_piysan(reference_no)
        return JSONResponse({"status": "success", "message": "Report submitted successfully!", "data": response})
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": str(e)},
            status_code=400,
        )


@router.post("/piysan/skip/{reference_no}")
async def toggle_skip(reference_no: str, request: Request):
    """Toggle the skipped status of a booking."""
    if not _authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    is_skipped = None
    if request.headers.get("content-type") == "application/json":
        try:
            body = await request.json()
            is_skipped = body.get("is_skipped")
        except Exception:
            pass

    new_state = toggle_skip_booking(reference_no, is_skipped=is_skipped)
    return JSONResponse({"status": "success", "reference_no": reference_no, "is_skipped": new_state})


@router.post("/piysan/submit-capture/{raw_capture_id}")
async def manual_submit_capture(raw_capture_id: int, request: Request):
    """Manually submit results associated with a specific raw capture ID to Piysan LIS."""
    if not _authed(request):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not logged in")

    from app.services.database import load_raw_capture
    capture = load_raw_capture(raw_capture_id)
    if not capture:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Raw capture not found")

    from app.services import report_generator
    try:
        report = report_generator.generate_report(
            capture["payload"],
            source="ui",
            raw_capture_id=raw_capture_id,
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to parse ASTM capture: {e}")

    reference_no = report.get("order", {}).get("sample_id")
    if not reference_no:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No sample ID/barcode found in capture")

    try:
        response = manual_submit_to_piysan(reference_no)
        return JSONResponse(
            {
                "status": "success",
                "message": f"Successfully pushed results for order {reference_no} to Piysan LIS!",
                "data": response,
            }
        )
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Piysan LIS push failed: {e}"},
            status_code=400,
        )
