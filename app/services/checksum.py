"""ASTM E1381 frame checksum computation and verification.

An ASTM frame has the wire form::

    <STX> FN text <ETX|ETB> C1 C2 <CR> <LF>

The checksum ``C1 C2`` is the modulo-256 sum of every byte starting with the
frame number and ending with (and including) the terminator byte
(``ETX``/``ETB``), rendered as two uppercase ASCII hex digits.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.utils.logger import get_logger

logger = get_logger(__name__)

STX = 0x02
ETX = 0x03
ETB = 0x17
CR = 0x0D
LF = 0x0A


@dataclass(frozen=True)
class ChecksumResult:
    expected: str
    actual: str

    @property
    def is_valid(self) -> bool:
        return self.expected == self.actual


def compute_checksum(payload: bytes) -> str:
    """Compute the ASTM checksum for ``payload``.

    ``payload`` must be the bytes starting at the frame number and ending
    with (and including) the ETX/ETB terminator byte.
    """
    total = sum(payload) % 256
    return f"{total:02X}"


def verify_frame(raw_frame: bytes) -> ChecksumResult:
    """Verify the checksum of a complete raw frame (including STX/CR/LF).

    Raises ``ValueError`` if the frame is structurally too short or missing
    STX/terminator bytes.
    """
    if len(raw_frame) < 6 or raw_frame[0] != STX:
        raise ValueError("Frame does not start with STX; cannot verify checksum")

    terminator_index = None
    for idx, byte in enumerate(raw_frame):
        if byte in (ETX, ETB):
            terminator_index = idx
            break
    if terminator_index is None:
        raise ValueError("Frame has no ETX/ETB terminator; cannot verify checksum")

    payload = raw_frame[1:terminator_index + 1]  # frame# .. terminator, inclusive
    checksum_bytes = raw_frame[terminator_index + 1: terminator_index + 3]
    if len(checksum_bytes) != 2:
        raise ValueError("Frame is missing 2-byte checksum after terminator")

    expected = checksum_bytes.decode("ascii", errors="replace").upper()
    actual = compute_checksum(payload)
    return ChecksumResult(expected=expected, actual=actual)
