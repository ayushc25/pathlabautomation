"""Top-level ASTM parsing orchestration.

Wires together frame reassembly (``frame_reassembler``), record tokenising
(``record_parser``), and the specialised decoders (``result_decoder``,
``histogram_decoder``, ``matrix_decoder``) into one structured result.

Malformed individual records are logged and skipped so that one bad record
never aborts decoding of the rest of the capture (per the error-handling
requirement).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from app.services import frame_reassembler
from app.services.histogram_decoder import decode_histogram
from app.services.matrix_decoder import decode_matrix
from app.services.record_parser import (
    parse_comment,
    parse_fields,
    parse_header,
    parse_order,
    parse_patient,
    parse_terminator,
    record_type_of,
    split_records,
)
from app.services.result_decoder import parse_result_record
from app.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_RECORD_TYPES = {"H", "P", "O", "R", "C", "M", "L"}


class ASTMParseError(Exception):
    """Raised when the capture cannot be parsed at all (e.g. empty file)."""


@dataclass
class ParsedASTM:
    header: Dict[str, Any] = field(default_factory=dict)
    patient: Dict[str, Any] = field(default_factory=dict)
    order: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    comments: List[Dict[str, Any]] = field(default_factory=list)
    histograms: Dict[str, Any] = field(default_factory=dict)
    matrices: Dict[str, Any] = field(default_factory=dict)
    terminators: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checksum_failures: int = 0
    frames_parsed: int = 0
    records_parsed: int = 0
    records_skipped: int = 0


def parse_capture(capture_text: str) -> ParsedASTM:
    """Parse a logged capture file's text (the 'Received:'/'HEX :'/'ASCII:'
    format saved by the analyzer's host-connection logger, or uploaded via
    the /decode API)."""
    if not capture_text or not capture_text.strip():
        raise ASTMParseError("Capture file is empty")

    reassembly = frame_reassembler.reassemble(capture_text)
    return _build_parsed_astm(
        reassembly,
        empty_message=(
            "No ASTM frames could be extracted from this file — "
            "expected 'Received:' blocks with HEX or ASCII payloads"
        ),
    )


def parse_capture_bytes(raw_bytes: bytes) -> ParsedASTM:
    """Parse raw bytes received directly from the analyzer's TCP socket -
    the real wire protocol (STX/ETX/ETB frames with checksums), not a logged
    capture file. Use this for live socket data; use ``parse_capture`` for
    text already in the logged file format."""
    if not raw_bytes:
        raise ASTMParseError("Analyzer transmission is empty")

    reassembly = frame_reassembler.reassemble_live(raw_bytes)
    return _build_parsed_astm(
        reassembly,
        empty_message="No ASTM frames could be extracted from the analyzer transmission",
    )


def _build_parsed_astm(reassembly, empty_message: str) -> ParsedASTM:
    result = ParsedASTM(warnings=list(reassembly.warnings))

    if not reassembly.messages:
        raise ASTMParseError(empty_message)

    result.frames_parsed = sum(len(m.frames) for m in reassembly.messages)
    result.checksum_failures = sum(
        1 for m in reassembly.messages for f in m.frames if f.checksum_valid is False
    )

    last_comment_context: str | None = None

    for message in reassembly.messages:
        for record_text in split_records(message.text):
            record_type = record_type_of(record_text)
            if record_type not in SUPPORTED_RECORD_TYPES:
                result.warnings.append(f"Skipping unsupported record type: {record_type!r}")
                result.records_skipped += 1
                continue

            fields = parse_fields(record_text)
            try:
                if record_type == "H":
                    result.header = parse_header(fields)
                elif record_type == "P":
                    result.patient = parse_patient(fields)
                elif record_type == "O":
                    result.order = parse_order(fields)
                    last_comment_context = None
                elif record_type == "R":
                    parsed = parse_result_record(fields)
                    if parsed is None:
                        result.records_skipped += 1
                        continue
                    result.results[parsed["parameter"]] = parsed["entry"]
                    last_comment_context = parsed["parameter"]
                elif record_type == "C":
                    comment = parse_comment(fields)
                    comment["measurement"] = last_comment_context
                    result.comments.append(comment)
                elif record_type == "M":
                    subtype = fields[2].upper() if len(fields) > 2 else ""
                    if subtype == "HISTOGRAM":
                        histogram = decode_histogram(fields)
                        if histogram is None:
                            result.records_skipped += 1
                            continue
                        key = histogram.get("name") or histogram["type"]
                        result.histograms[key] = histogram
                    elif subtype == "MATRIX":
                        matrix = decode_matrix(fields)
                        if matrix is None:
                            result.records_skipped += 1
                            continue
                        key = matrix.get("name") or matrix["type"]
                        result.matrices[key] = matrix
                    else:
                        result.warnings.append(f"Unknown M record subtype: {subtype!r}")
                        result.records_skipped += 1
                        continue
                elif record_type == "L":
                    result.terminators.append(parse_terminator(fields))
            except Exception:  # noqa: BLE001 - never let one bad record kill the batch
                logger.exception("Failed to parse %s record, skipping: %r", record_type, record_text)
                result.warnings.append(f"Failed to parse {record_type} record: {record_text[:80]!r}")
                result.records_skipped += 1
                continue

            result.records_parsed += 1

    if result.checksum_failures:
        result.warnings.append(
            f"{result.checksum_failures} frame(s) failed checksum verification"
        )

    return result
