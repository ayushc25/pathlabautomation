"""Decodes ASTM M (Manufacturer) records carrying ``MATRIX`` (scattergram)
payloads into (x, y) point clouds.

Same base64/deflate/float32 pipeline as histograms (see
``histogram_decoder.decode_float_stream``), but the resulting float stream
is interpreted as interleaved x/y coordinate pairs rather than bin heights.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.histogram_decoder import PayloadDecodeError, decode_float_stream
from app.services.record_parser import safe_get
from app.utils.logger import get_logger

logger = get_logger(__name__)


def decode_matrix(fields: List[str]) -> Optional[Dict[str, Any]]:
    """Decode a MATRIX M record's fields into ``{"type", "name", "points"}``."""
    matrix_type = safe_get(fields, 3) or "UNKNOWN"
    name = safe_get(fields, 4) or None
    payload_field = safe_get(fields, 5)
    if not payload_field:
        logger.warning("MATRIX record has no payload field: %r", fields)
        return None

    try:
        values = decode_float_stream(payload_field)
    except PayloadDecodeError as exc:
        logger.warning("Failed to decode matrix %s: %s", matrix_type, exc)
        return None

    if len(values) % 2 != 0:
        logger.warning(
            "MATRIX %s has an odd float count (%d); dropping trailing value",
            matrix_type, len(values),
        )
        values = values[:-1]

    points = [
        {"x": float(values[i]), "y": float(values[i + 1])}
        for i in range(0, len(values), 2)
    ]
    return {
        "type": matrix_type,
        "name": name,
        "points": points,
    }
