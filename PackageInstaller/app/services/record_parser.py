"""Generic ASTM record tokenising helpers plus parsers for the structural
records (H, P, O, C, L). R (result) and M (histogram/matrix) records have
their own dedicated decoders since their payloads need real transformation
rather than positional field extraction.

Field/positions below follow the standard ASTM E1394/LIS2 record layout that
the HORIBA Yumizen H500/H500E "Output Format for Host Connection" (RAA085BEN)
specification is based on. Only *structural* positions are hardcoded here
(e.g. "field 8 of a P record is sex") — actual parameter names/values are
always read from the data itself, never hardcoded.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

FIELD_SEP = "|"
REPEAT_SEP = "\\"
COMPONENT_SEP = "^"
ESCAPE_SEP = "&"


def split_records(logical_text: str) -> List[str]:
    """Split a reassembled logical message into individual ASTM records."""
    parts = re.split(r"[\r\n]+", logical_text)
    return [p for p in parts if p.strip()]


def parse_fields(record_text: str) -> List[str]:
    return record_text.split(FIELD_SEP)


def split_components(value: str) -> List[str]:
    return value.split(COMPONENT_SEP) if value else []


def split_repeats(value: str) -> List[str]:
    return value.split(REPEAT_SEP) if value else []


def safe_get(fields: List[str], idx: int, default: str = "") -> str:
    return fields[idx] if 0 <= idx < len(fields) else default


def record_type_of(record_text: str) -> Optional[str]:
    """Return the single-letter record type (H/P/O/R/C/M/L/...) of a record."""
    if not record_text:
        return None
    return record_text[0].upper()


def parse_header(fields: List[str]) -> Dict[str, Any]:
    return {
        "delimiters": safe_get(fields, 1),
        "message_control_id": safe_get(fields, 2),
        "sender_name": safe_get(fields, 4),
        "sender_address": safe_get(fields, 5),
        "sender_phone": safe_get(fields, 7),
        "receiver_id": safe_get(fields, 9),
        "processing_id": safe_get(fields, 11),
        "version": safe_get(fields, 12),
        "datetime": safe_get(fields, 13),
    }


def parse_patient(fields: List[str]) -> Dict[str, Any]:
    name_components = split_components(safe_get(fields, 5))
    patient_id = safe_get(fields, 4) or safe_get(fields, 3) or safe_get(fields, 2)
    return {
        "patient_id": patient_id or None,
        "name": {
            "last": name_components[0] if len(name_components) > 0 and name_components[0] else None,
            "first": name_components[1] if len(name_components) > 1 and name_components[1] else None,
            "middle": name_components[2] if len(name_components) > 2 and name_components[2] else None,
        },
        "dob": safe_get(fields, 7) or None,
        "sex": safe_get(fields, 8) or None,
        "race": safe_get(fields, 9) or None,
        "physician": safe_get(fields, 13) or None,
        "height": safe_get(fields, 16) or None,
        "weight": safe_get(fields, 17) or None,
    }


def _parse_test_id(component_field: str) -> Optional[str]:
    """Universal test ID fields look like ``^^^WBC`` — the analyte code is
    the last non-empty component."""
    components = [c for c in split_components(component_field) if c]
    return components[-1] if components else None


def parse_order(fields: List[str]) -> Dict[str, Any]:
    tests = [
        _parse_test_id(repeat)
        for repeat in split_repeats(safe_get(fields, 4))
    ]
    return {
        "sample_id": safe_get(fields, 2) or None,
        "instrument_sample_id": safe_get(fields, 3) or None,
        "tests": [t for t in tests if t],
        "priority": safe_get(fields, 5) or None,
        "collection_datetime": safe_get(fields, 6) or None,
        "collection_end_datetime": safe_get(fields, 7) or None,
        "action_code": safe_get(fields, 11) or None,
        "report_type": safe_get(fields, 25) or None,
    }


def parse_comment(fields: List[str]) -> Dict[str, Any]:
    comment_components = [c for c in split_components(safe_get(fields, 3)) if c]
    comment_type_field = safe_get(fields, 4) or (comment_components[0] if len(comment_components) > 1 else None)
    description = comment_components[-1] if comment_components else safe_get(fields, 3)
    return {
        "source": safe_get(fields, 2) or None,
        "alarm_type": comment_type_field,
        "description": description or None,
        "raw": safe_get(fields, 3),
    }


def parse_terminator(fields: List[str]) -> Dict[str, Any]:
    return {
        "termination_code": safe_get(fields, 2) or None,
    }
