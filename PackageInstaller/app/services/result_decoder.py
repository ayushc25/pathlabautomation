"""Decodes ASTM R (Result) records into the API's ``results`` JSON shape.

Parameter names are never hardcoded — they are read straight out of each
record's universal test ID field, so any analyte the instrument reports
(WBC, RBC, HGB, custom research parameters, ...) round-trips correctly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.record_parser import (
    safe_get,
    split_components,
    split_repeats,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _coerce_value(raw: str) -> Any:
    if raw == "":
        return None
    try:
        if "." in raw or "e" in raw.lower():
            return float(raw)
        return int(raw)
    except ValueError:
        try:
            return float(raw)
        except ValueError:
            return raw


def _parse_reference_range(raw: str) -> Optional[Dict[str, Any]]:
    """Parse an R record's reference-range field.

    Per ASTM, this field is itself componentised as
    ``<range-text>^<range-type>`` (e.g. ``"32.0 - 35.0^REFERENCE_RANGE"``) —
    the range type (REFERENCE_RANGE, AGE_RANGE, ...) is metadata about the
    range, not a second boundary value, so it must not be read as "high".
    """
    if not raw:
        return None
    components = split_components(raw)
    range_text = components[0] if components else raw
    range_type = components[1] if len(components) > 1 and components[1] else None

    if "-" in range_text:
        low, high = range_text.split("-", 1)
        parsed: Dict[str, Any] = {
            "low": _coerce_value(low.strip()),
            "high": _coerce_value(high.strip()),
        }
    else:
        parsed = {"raw": range_text}

    if range_type:
        parsed["type"] = range_type
    return parsed


def parse_result_record(fields: List[str]) -> Optional[Dict[str, Any]]:
    """Parse a single R record's fields into ``(parameter_name, entry)``.

    Returns ``None`` (and logs a warning) if the record is too malformed to
    identify a parameter name, so the caller can skip it and keep decoding
    the rest of the message.
    """
    test_id_field = safe_get(fields, 2)
    components = [c for c in split_components(test_id_field) if c]
    parameter = components[-1] if components else None
    if not parameter:
        logger.warning("R record missing a resolvable parameter name: %r", fields)
        return None

    value_raw = safe_get(fields, 3)
    entry: Dict[str, Any] = {
        "value": _coerce_value(value_raw),
        "unit": safe_get(fields, 4) or None,
        "reference_range": _parse_reference_range(safe_get(fields, 5)),
        "flags": [f for f in split_repeats(safe_get(fields, 6)) if f],
        "status": safe_get(fields, 8) or None,
        "timestamp": safe_get(fields, 12) or safe_get(fields, 11) or None,
    }
    return {"parameter": parameter, "entry": entry}


def decode_results(record_field_lists: List[List[str]]) -> Dict[str, Any]:
    """Decode all R records in a message into the flat results dict, e.g.::

        {"WBC": {"value": 6.42, "unit": "10^3/uL", ...}, ...}
    """
    results: Dict[str, Any] = {}
    for fields in record_field_lists:
        try:
            parsed = parse_result_record(fields)
        except Exception:  # noqa: BLE001 - defensive: never abort the batch
            logger.exception("Failed to parse R record, skipping: %r", fields)
            continue
        if parsed is None:
            continue
        results[parsed["parameter"]] = parsed["entry"]
    return results
