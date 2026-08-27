"""``/decode`` endpoint: accepts a raw ASTM capture .txt file and returns the
fully decoded HORIBA Yumizen H500/H500E result set."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services import astm_parser, report_generator
from app.services.database import save_raw_capture
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(tags=["decode"])


@router.post(
    "/decode",
    summary="Decode a HORIBA Yumizen H500/H500E ASTM capture file",
    response_model_exclude_none=False,
)
async def decode_astm_file(file: UploadFile = File(..., description="Raw ASTM capture .txt file")) -> dict:
    if file.filename and not file.filename.lower().endswith(".txt"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Expected a .txt capture file, got: {file.filename!r}",
        )

    raw_bytes = await file.read()
    if not raw_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")

    try:
        capture_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        capture_text = raw_bytes.decode("latin-1")
        logger.warning("File %s was not valid UTF-8; decoded as latin-1", file.filename)

    session_id = uuid.uuid4().hex[:8]
    raw_capture_id = save_raw_capture(
        source="api",
        filename=file.filename,
        payload=capture_text,
    )

    try:
        report = report_generator.generate_report(
            capture_text,
            session_id=session_id,
            source="api",
            raw_capture_id=raw_capture_id,
        )
    except astm_parser.ASTMParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected failure decoding %s", file.filename)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error while decoding capture: {exc}",
        ) from exc

    return report
