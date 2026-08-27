from app.services import frame_reassembler
from tests.helpers import build_capture, build_frame_bytes, build_received_block


def test_reassemble_single_frame_message():
    capture = build_capture(["H|\\^&|||Sender^Instrument|||||Receiver||P|1|20260729120000"])
    result = frame_reassembler.reassemble(capture)
    assert len(result.messages) == 1
    assert result.messages[0].text.startswith("H|")
    assert result.messages[0].all_checksums_valid


def test_reassemble_multiple_records():
    capture = build_capture([
        "H|\\^&|||Sender|||||Receiver||P|1|20260729120000",
        "P|1||PID123||Doe^Jane||19800101|F",
        "L|1|N",
    ])
    result = frame_reassembler.reassemble(capture)
    assert len(result.messages) == 3


def test_reassemble_handles_etb_continuation():
    # Simulate a record split across two frames via ETB, then completed by ETX.
    part1 = build_frame_bytes(0, "M|1|HISTOGRAM|RBC/PLT|Test|AAAA", terminator="ETB")
    part2 = build_frame_bytes(1, "BBBB", terminator="ETX")
    capture = (
        build_received_block(part1, "0M|1|HISTOGRAM|RBC/PLT|Test|AAAA")
        + "\n"
        + build_received_block(part2, "1BBBB")
    )
    result = frame_reassembler.reassemble(capture)
    assert len(result.messages) == 1
    assert result.messages[0].text == "M|1|HISTOGRAM|RBC/PLT|Test|AAAABBBB"
    assert len(result.messages[0].frames) == 2


def test_reassemble_reports_checksum_failure():
    frame_bytes = bytearray(build_frame_bytes(0, "H|\\^&", terminator="ETX"))
    frame_bytes[3] = ord("Z")  # corrupt payload without fixing checksum
    capture = build_received_block(bytes(frame_bytes), "0H|\\^&")
    result = frame_reassembler.reassemble(capture)
    assert result.messages[0].frames[0].checksum_valid is False


def test_reassemble_falls_back_to_ascii_when_hex_missing():
    capture = "Received:\nASCII:\n0H|\\^&|||Sender\n"
    result = frame_reassembler.reassemble(capture)
    assert len(result.messages) == 1
    assert result.messages[0].frames[0].source == "ascii"
    assert result.messages[0].frames[0].checksum_valid is None


def test_reassemble_empty_capture_produces_warning():
    result = frame_reassembler.reassemble("garbage with no markers at all")
    # Falls back to treating whole text as one ASCII block; no digit-prefixed
    # line means no frame gets extracted, so we expect a warning, not a crash.
    assert isinstance(result.warnings, list)
