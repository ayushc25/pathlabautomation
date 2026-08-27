from app.services.histogram_decoder import decode_histogram, decode_float_stream
from app.services.record_parser import parse_fields
from tests.helpers import deflate_base64_floats


def test_decode_float_stream_round_trips_values():
    values = [0.0, 1.5, -3.25, 100.0]
    b64 = deflate_base64_floats(values)
    payload_field = f"FLOATLE-stream/deflate:base64^{b64}"
    decoded = decode_float_stream(payload_field)
    assert list(decoded) == values


def test_decode_histogram_from_full_record():
    values = [float(i) for i in range(10)]
    b64 = deflate_base64_floats(values)
    record = f"M|2|HISTOGRAM|RBC/PLT|PltAlongRes|FLOATLE-stream/deflate:base64^{b64}"
    fields = parse_fields(record)
    histogram = decode_histogram(fields)
    assert histogram["type"] == "RBC/PLT"
    assert histogram["name"] == "PltAlongRes"
    assert histogram["x"] == list(range(10))
    assert histogram["y"] == values


def test_decode_histogram_handles_malformed_payload_gracefully():
    record = "M|2|HISTOGRAM|RBC/PLT|PltAlongRes|FLOATLE-stream/deflate:base64^not-valid-base64!!!"
    fields = parse_fields(record)
    assert decode_histogram(fields) is None


def test_decode_histogram_missing_payload_field():
    fields = parse_fields("M|2|HISTOGRAM|RBC/PLT|PltAlongRes")
    assert decode_histogram(fields) is None
