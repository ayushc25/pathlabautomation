from app.services.checksum import STX, ETX, compute_checksum, verify_frame


def test_compute_checksum_matches_known_astm_example():
    # "1H|\^&" + ETX -> payload bytes are frame#..ETX inclusive
    payload = b"1H|\\^&" + bytes([ETX])
    checksum = compute_checksum(payload)
    assert len(checksum) == 2
    assert checksum == checksum.upper()
    # Recompute manually to double check the modulo-256 sum logic.
    assert checksum == f"{sum(payload) % 256:02X}"


def test_verify_frame_accepts_valid_frame():
    payload = b"1H|\\^&" + bytes([ETX])
    checksum = compute_checksum(payload)
    frame = bytes([STX]) + payload + checksum.encode("ascii") + b"\r\n"
    result = verify_frame(frame)
    assert result.is_valid
    assert result.expected == result.actual


def test_verify_frame_detects_corruption():
    payload = b"1H|\\^&" + bytes([ETX])
    checksum = compute_checksum(payload)
    frame = bytearray(bytes([STX]) + payload + checksum.encode("ascii") + b"\r\n")
    frame[3] = ord("X")  # corrupt a payload byte after computing checksum
    result = verify_frame(bytes(frame))
    assert not result.is_valid


def test_verify_frame_raises_on_missing_stx():
    import pytest

    with pytest.raises(ValueError):
        verify_frame(b"no stx here")
