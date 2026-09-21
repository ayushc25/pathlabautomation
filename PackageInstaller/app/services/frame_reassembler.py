"""Extracts ASTM frames from a raw HORIBA capture log and reassembles
ETB-continued frames into complete logical messages.

The capture files produced by the analyzer's host-connection logger look
like::

    Received:
    HEX : 02344D7C327C484953544F4752414D...038B0D0A
    RAW : b'...'
    ASCII:
    4M|2|HISTOGRAM|RBC/PLT|PltAlongRes|FLOATLE-stream/deflate:base64^Y2AAAQ...

This module ignores the ``Received:``/``RAW :`` bookkeeping lines and pulls
the real frame bytes from the ``HEX :`` line (preferred, since it lets us
verify the checksum) or, if hex is unavailable/unparsable, falls back to the
plain ``ASCII:`` text (checksum verification is skipped in that case).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from app.services.checksum import ETB, ETX, STX, verify_frame
from app.utils.logger import get_logger

logger = get_logger(__name__)

_RECEIVED_BLOCK_RE = re.compile(r"Received:\s*\r?\n(.*?)(?=\r?\nReceived:|\Z)", re.DOTALL)
_HEX_LINE_RE = re.compile(r"HEX\s*:\s*([0-9A-Fa-f\s]+)")
_ASCII_BLOCK_RE = re.compile(
    r"ASCII\s*:\s*\r?\n?(.*?)(?=\r?\n\s*(?:HEX\s*:|RAW\s*:|Received:)|\Z)", re.DOTALL
)


@dataclass
class Frame:
    """A single decoded ASTM frame (post STX, pre CR/LF)."""

    frame_number: Optional[str]
    text: str
    terminator: str  # "ETX" or "ETB"
    checksum_valid: Optional[bool]
    source: str  # "hex" or "ascii"


@dataclass
class LogicalMessage:
    """One or more frames reassembled into a complete ASTM message body."""

    text: str
    frames: List[Frame] = field(default_factory=list)

    @property
    def all_checksums_valid(self) -> bool:
        results = [f.checksum_valid for f in self.frames if f.checksum_valid is not None]
        return all(results) if results else True


@dataclass
class ReassemblyResult:
    messages: List[LogicalMessage]
    warnings: List[str]


def _parse_frame_from_bytes(raw: bytes) -> Optional[Frame]:
    if not raw or raw[0] != STX:
        logger.warning("Frame does not start with STX; skipping malformed frame")
        return None

    terminator_index = None
    terminator_byte = None
    for idx in range(1, len(raw)):
        if raw[idx] in (ETX, ETB):
            terminator_index = idx
            terminator_byte = raw[idx]
            break
    if terminator_index is None:
        logger.warning("Frame has no ETX/ETB terminator; skipping malformed frame")
        return None

    body = raw[1:terminator_index]
    if not body:
        logger.warning("Frame body is empty after STX; skipping")
        return None

    frame_number = chr(body[0]) if 0x30 <= body[0] <= 0x37 else None
    text_bytes = body[1:] if frame_number is not None else body
    if text_bytes.endswith(b"\r"):
        text_bytes = text_bytes[:-1]

    checksum_valid: Optional[bool] = None
    try:
        result = verify_frame(raw[: terminator_index + 3])
        checksum_valid = result.is_valid
        if not checksum_valid:
            logger.warning(
                "Checksum mismatch for frame %s: expected=%s actual=%s",
                frame_number, result.expected, result.actual,
            )
    except ValueError as exc:
        logger.warning("Could not verify checksum: %s", exc)

    return Frame(
        frame_number=frame_number,
        text=text_bytes.decode("ascii", errors="replace"),
        terminator="ETX" if terminator_byte == ETX else "ETB",
        checksum_valid=checksum_valid,
        source="hex",
    )


def _parse_frame_from_ascii(line: str) -> Frame:
    """Best-effort fallback when raw hex bytes aren't available.

    The ASCII log line still carries the leading frame-number digit (e.g.
    ``"4M|2|..."``); we strip it if present. Checksum cannot be verified
    from ASCII alone.
    """
    frame_number = None
    text = line
    if line and line[0].isdigit() and len(line) > 1 and line[1].isalpha():
        frame_number = line[0]
        text = line[1:]
    return Frame(
        frame_number=frame_number,
        text=text,
        terminator="ETX",
        checksum_valid=None,
        source="ascii",
    )


def _clean_hex(raw_hex: str) -> str:
    return re.sub(r"\s+", "", raw_hex)


def _join_into_messages(frames: List[Frame]) -> tuple[List[LogicalMessage], List[str]]:
    """Reassemble ETB-continued frames into complete logical messages."""
    warnings: List[str] = []
    messages: List[LogicalMessage] = []
    buffer_text = ""
    buffer_frames: List[Frame] = []
    for frame in frames:
        buffer_text += frame.text
        buffer_frames.append(frame)
        if frame.terminator == "ETX":
            messages.append(LogicalMessage(text=buffer_text, frames=buffer_frames))
            buffer_text = ""
            buffer_frames = []

    if buffer_text:
        warnings.append("Capture ended mid-message (unterminated ETB sequence); flushing partial data")
        messages.append(LogicalMessage(text=buffer_text, frames=buffer_frames))

    return messages, warnings


def reassemble(capture_text: str) -> ReassemblyResult:
    """Parse a raw capture text file into reassembled logical ASTM messages."""
    warnings: List[str] = []
    blocks = _RECEIVED_BLOCK_RE.findall(capture_text)
    if not blocks:
        # No "Received:" markers found — treat the whole file as one ASCII blob.
        blocks = [capture_text]

    frames: List[Frame] = []
    for block_index, block in enumerate(blocks):
        hex_match = _HEX_LINE_RE.search(block)
        frame: Optional[Frame] = None
        if hex_match:
            cleaned = _clean_hex(hex_match.group(1))
            if len(cleaned) % 2 == 0 and cleaned:
                try:
                    raw_bytes = bytes.fromhex(cleaned)
                    frame = _parse_frame_from_bytes(raw_bytes)
                except ValueError as exc:
                    warnings.append(f"Block {block_index}: invalid hex payload ({exc})")
            else:
                warnings.append(f"Block {block_index}: HEX line has odd length, skipping hex parse")

        if frame is None:
            ascii_match = _ASCII_BLOCK_RE.search(block)
            if ascii_match:
                for line in ascii_match.group(1).splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    frame = _parse_frame_from_ascii(line)
                    frames.append(frame)
                    frame = None  # already appended; avoid double-append below
                continue
            warnings.append(f"Block {block_index}: no usable HEX or ASCII payload found; skipped")
            continue

        frames.append(frame)

    if not frames:
        warnings.append("No ASTM frames could be extracted from the capture file")

    messages, join_warnings = _join_into_messages(frames)
    warnings.extend(join_warnings)
    return ReassemblyResult(messages=messages, warnings=warnings)


def extract_live_frames(data: bytes) -> tuple[List[Frame], List[str]]:
    """Scan a raw byte stream straight off the wire (no log-file wrapping) for
    ASTM frames: <STX> FN text <ETX|ETB> C1 C2 <CR><LF>.

    Handshake bytes (ENQ/ACK/EOT) and anything else between frames are simply
    skipped - only STX...terminator+checksum spans are extracted.
    """
    warnings: List[str] = []
    frames: List[Frame] = []
    pos = 0
    length = len(data)
    while pos < length:
        stx_index = data.find(bytes([STX]), pos)
        if stx_index == -1:
            break

        terminator_index = None
        for idx in range(stx_index + 1, length):
            if data[idx] in (ETX, ETB):
                terminator_index = idx
                break
        if terminator_index is None:
            warnings.append(f"Frame at byte {stx_index}: no ETX/ETB terminator found; discarding trailing data")
            break

        frame_end = terminator_index + 3  # include the 2 checksum bytes
        if frame_end > length:
            warnings.append(f"Frame at byte {stx_index}: truncated before checksum; discarding trailing data")
            break

        raw_frame = data[stx_index:frame_end]
        frame = _parse_frame_from_bytes(raw_frame)
        if frame is not None:
            frames.append(frame)
        else:
            warnings.append(f"Frame at byte {stx_index}: could not be parsed; skipped")

        pos = frame_end

    if not frames:
        warnings.append("No ASTM frames could be extracted from the analyzer data")

    return frames, warnings


def reassemble_live(data: bytes) -> ReassemblyResult:
    """Parse a raw byte stream received directly from the analyzer socket
    (not a logged capture file) into reassembled logical ASTM messages."""
    frames, warnings = extract_live_frames(data)
    messages, join_warnings = _join_into_messages(frames)
    warnings.extend(join_warnings)
    return ReassemblyResult(messages=messages, warnings=warnings)
