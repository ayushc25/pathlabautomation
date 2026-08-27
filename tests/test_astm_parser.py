from app.services import astm_parser
from tests.helpers import build_capture, deflate_base64_floats


def _sample_records():
    hist_b64 = deflate_base64_floats([float(i) for i in range(5)])
    matrix_b64 = deflate_base64_floats([1.0, 2.0, 3.0, 4.0])
    return [
        "H|\\^&|||Instrument^H500|||||Receiver||P|1|20260729120000",
        "P|1||PID123||Doe^Jane||19800101|F|||||Dr.Smith",
        "O|1|SAMP001||^^^WBC\\^^^RBC|||20260729120000",
        "R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F|||20260729120500",
        "R|2|^^^RBC|4.81|10^6/uL|4.20-6.10|N||F|||20260729120500",
        "C|1|I|^^High WBC alert|G",
        f"M|1|HISTOGRAM|RBC/PLT|PltAlongRes|FLOATLE-stream/deflate:base64^{hist_b64}",
        f"M|2|MATRIX|LMNE|LMNEResAbs|FLOATLE-stream/deflate:base64^{matrix_b64}",
        "L|1|N",
    ]


def test_parse_capture_end_to_end():
    capture = build_capture(_sample_records())
    parsed = astm_parser.parse_capture(capture)

    assert parsed.patient["patient_id"] == "PID123"
    assert parsed.patient["sex"] == "F"
    assert parsed.order["sample_id"] == "SAMP001"
    assert parsed.order["tests"] == ["WBC", "RBC"]

    assert parsed.results["WBC"]["value"] == 6.42
    assert parsed.results["RBC"]["value"] == 4.81

    assert len(parsed.comments) == 1
    assert parsed.comments[0]["measurement"] == "RBC"  # last R before the C record

    assert "PltAlongRes" in parsed.histograms
    assert parsed.histograms["PltAlongRes"]["type"] == "RBC/PLT"

    assert "LMNEResAbs" in parsed.matrices
    assert parsed.matrices["LMNEResAbs"]["type"] == "LMNE"

    assert parsed.checksum_failures == 0
    assert parsed.records_parsed == 9


def test_parse_capture_raises_on_empty_input():
    import pytest

    with pytest.raises(astm_parser.ASTMParseError):
        astm_parser.parse_capture("")


def test_parse_capture_skips_malformed_record_and_continues():
    records = _sample_records()
    records.insert(3, "R|9|^^^|not-a-number")  # unresolvable parameter -> should be skipped
    capture = build_capture(records)
    parsed = astm_parser.parse_capture(capture)
    assert parsed.records_skipped >= 1
    assert parsed.results["WBC"]["value"] == 6.42
