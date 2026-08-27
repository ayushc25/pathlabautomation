"""Shared test helpers for building synthetic-but-valid ASTM captures."""
from __future__ import annotations

import base64
import struct
import zlib
from typing import Iterable, List

from app.services.checksum import STX, ETB, ETX, compute_checksum


def build_frame_bytes(frame_number: int, text: str, terminator: str = "ETX") -> bytes:
    """Build a complete, checksum-valid raw ASTM frame (STX..CRLF)."""
    term_byte = ETX if terminator == "ETX" else ETB
    body = (str(frame_number % 8) + text).encode("ascii") + bytes([term_byte])
    checksum = compute_checksum(body)
    return bytes([STX]) + body + checksum.encode("ascii") + b"\r\n"


def build_received_block(frame_bytes: bytes, ascii_text: str) -> str:
    hex_str = frame_bytes.hex().upper()
    return (
        "Received:\n"
        f"HEX : {hex_str}\n"
        f"RAW : {frame_bytes!r}\n"
        "ASCII:\n"
        f"{ascii_text}\n"
    )


def build_capture(records: Iterable[str]) -> str:
    """Build a full synthetic capture file text from a list of record
    strings (each not including the leading frame-number digit)."""
    blocks: List[str] = []
    for i, record_text in enumerate(records):
        frame_number = i % 8
        frame_bytes = build_frame_bytes(frame_number, record_text, terminator="ETX")
        ascii_text = f"{frame_number}{record_text}"
        blocks.append(build_received_block(frame_bytes, ascii_text))
    return "\n".join(blocks)


def deflate_base64_floats(values: List[float]) -> str:
    """Encode a list of floats through the FLOATLE-stream/deflate:base64
    pipeline used by HORIBA M records."""
    raw = struct.pack(f"<{len(values)}f", *values)
    compressed = zlib.compress(raw)
    return base64.b64encode(compressed).decode("ascii")
