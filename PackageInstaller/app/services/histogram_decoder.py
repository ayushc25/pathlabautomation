"""Decodes ASTM M (Manufacturer) records carrying ``HISTOGRAM`` payloads.

Payload pipeline, as described in the HORIBA RAA085BEN spec::

    base64 decode -> zlib inflate -> little-endian float32 stream -> numpy array

M record field layout (after the leading frame-number byte has been
stripped by the frame reassembler)::

    M | seq | HISTOGRAM | <channel/type> | <name> | <format>^<base64 payload>
"""
from __future__ import annotations

import base64
import struct
import zlib
from typing import Any, Dict, List, Optional

import numpy as np

from app.services.record_parser import safe_get, split_components
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PayloadDecodeError(Exception):
    """Raised when a base64/deflate/float payload cannot be decoded."""


def decode_float_stream(payload_field: str) -> np.ndarray:
    """Decode a ``<format-descriptor>^<base64>`` payload field into a
    NumPy float32 array.

    Supports the ``FLOATLE-stream/deflate:base64`` pipeline documented by
    HORIBA: base64 decode -> zlib inflate -> little-endian float32 unpack.
    Raises ``PayloadDecodeError`` with a descriptive message on failure.
    """
    parts = split_components(payload_field)
    if len(parts) < 2:
        raise PayloadDecodeError(
            f"Expected '<format>^<base64>' payload field, got: {payload_field!r}"
        )
    format_descriptor, b64_data = parts[0], "^".join(parts[1:])

    try:
        compressed = base64.b64decode(b64_data, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise PayloadDecodeError(f"Base64 decode failed: {exc}") from exc

    raw_bytes = compressed
    if "deflate" in format_descriptor.lower():
        try:
            raw_bytes = zlib.decompress(compressed)
        except zlib.error:
            try:
                # Fallback to raw deflate (no headers)
                raw_bytes = zlib.decompress(compressed, -zlib.MAX_WBITS)
            except zlib.error as exc:
                raise PayloadDecodeError(f"zlib inflate failed: {exc}") from exc

    if len(raw_bytes) % 4 != 0:
        raise PayloadDecodeError(
            f"Decompressed payload length {len(raw_bytes)} is not a multiple of 4 bytes"
        )

    count = len(raw_bytes) // 4
    try:
        values = struct.unpack(f"<{count}f", raw_bytes)
    except struct.error as exc:
        raise PayloadDecodeError(f"Float unpack failed: {exc}") from exc

    return np.asarray(values, dtype=np.float32)


def decode_histogram(fields: List[str]) -> Optional[Dict[str, Any]]:
    """Decode a HISTOGRAM M record's fields into ``{"type", "name", "x", "y"}``."""
    channel_type = safe_get(fields, 3) or "UNKNOWN"
    name = safe_get(fields, 4) or None
    payload_field = safe_get(fields, 5)
    if not payload_field:
        logger.warning("HISTOGRAM record has no payload field: %r", fields)
        return None

    try:
        y = decode_float_stream(payload_field)
    except PayloadDecodeError as exc:
        logger.warning("Failed to decode histogram %s: %s", channel_type, exc)
        return None

    x = np.arange(len(y), dtype=np.int64)
    return {
        "type": channel_type,
        "name": name,
        "x": x.tolist(),
        "y": y.tolist(),
    }
