"""Orchestrates the full decode pipeline: raw capture text -> parsed ASTM
structures -> rendered graphs -> final API response dict.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

from app.services import astm_parser
from app.services.database import load_latest_installation_mapping_lookup, save_decoded_capture
from app.services.graph_generator import (
    ARTIFACTS_DIR,
    generate_histogram_graph,
    generate_scattergram_graph,
)
from app.services.test_code_lookup import resolve_test_code
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Substrings matched (case-insensitively) against a histogram/matrix's
# type+name label to decide which standard graphs to auto-render.
HISTOGRAM_TARGETS = ["RBC", "PLT", "WBC"]
MATRIX_TARGETS = ["LMNE", "EOS"]


def _label(entry: Dict[str, Any]) -> str:
    return f"{entry.get('type') or ''} {entry.get('name') or ''}".upper()


def _enrich_results(results: Dict[str, Dict[str, Any]], result_key_map: Dict[str, str]) -> Dict[str, Dict[str, Any]]:
    enriched: Dict[str, Dict[str, Any]] = {}
    for code, entry in results.items():
        metadata = resolve_test_code(code) or {}
        mapped_code = result_key_map.get(code, code)
        enriched[mapped_code] = {
            "device_test_code": code,
            "lab_test_code": mapped_code if mapped_code != code else None,
            "test_name": metadata.get("name"),
            "panel": metadata.get("panel"),
            **entry,
        }
    return enriched


def generate_report(
    capture_data: Union[str, bytes, bytearray],
    session_id: Optional[str] = None,
    artifacts_dir: Path = ARTIFACTS_DIR,
    source: str = "api",
    raw_capture_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Decode a raw ASTM capture and return the full structured response.

    ``capture_data`` is either text in the logged capture-file format
    ('Received:'/'HEX :'/'ASCII:' blocks, as uploaded via /decode or stored
    from the UI) or raw bytes straight off the analyzer socket - the two use
    different frame extraction since only the live bytes carry real
    STX/ETX/ETB control characters.
    """
    if isinstance(capture_data, str) and '\x02' in capture_data:
        capture_data = capture_data.encode("latin-1")

    if isinstance(capture_data, (bytes, bytearray)):
        parsed = astm_parser.parse_capture_bytes(bytes(capture_data))
    else:
        parsed = astm_parser.parse_capture(capture_data)
    result_key_map = load_latest_installation_mapping_lookup()

    images: Dict[str, str] = {}
    matched_histogram_keys = set()
    for target in HISTOGRAM_TARGETS:
        for key, histogram in parsed.histograms.items():
            if key in matched_histogram_keys:
                continue
            if target in _label(histogram):
                path = generate_histogram_graph(key, histogram, output_dir=artifacts_dir, session_id=session_id)
                if path:
                    images[f"{target}_histogram"] = path
                matched_histogram_keys.add(key)
                break

    matched_matrix_keys = set()
    for target in MATRIX_TARGETS:
        for key, matrix in parsed.matrices.items():
            if key in matched_matrix_keys:
                continue
            if target in _label(matrix):
                path = generate_scattergram_graph(key, matrix, output_dir=artifacts_dir, session_id=session_id)
                if path:
                    images[f"{target}_scattergram"] = path
                matched_matrix_keys.add(key)
                break

    report = {
        "patient": parsed.patient,
        "order": parsed.order,
        "results": _enrich_results(parsed.results, result_key_map),
        "comments": parsed.comments,
        "histograms": parsed.histograms,
        "matrices": parsed.matrices,
        "images": images,
        "meta": {
            "header": parsed.header,
            "frames_parsed": parsed.frames_parsed,
            "records_parsed": parsed.records_parsed,
            "records_skipped": parsed.records_skipped,
            "checksum_failures": parsed.checksum_failures,
            "warnings": parsed.warnings,
        },
    }
    save_decoded_capture(source=source, payload=report, raw_capture_id=raw_capture_id)

    # Auto-submit results to Piysan if configured and enabled
    try:
        from app.services.piysan_service import trigger_auto_submit
        trigger_auto_submit(raw_capture_id, report)
    except Exception as e:
        logger.error("Failed to trigger Piysan auto-submission: %s", e)

    return report

