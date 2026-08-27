from app.services.matrix_decoder import decode_matrix
from app.services.record_parser import parse_fields
from tests.helpers import deflate_base64_floats


def test_decode_matrix_produces_xy_points():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]  # 3 points
    b64 = deflate_base64_floats(values)
    record = f"M|3|MATRIX|LMNE|LMNEResAbs|FLOATLE-stream/deflate:base64^{b64}"
    fields = parse_fields(record)
    matrix = decode_matrix(fields)
    assert matrix["type"] == "LMNE"
    assert matrix["name"] == "LMNEResAbs"
    assert matrix["points"] == [
        {"x": 1.0, "y": 2.0},
        {"x": 3.0, "y": 4.0},
        {"x": 5.0, "y": 6.0},
    ]


def test_decode_matrix_drops_trailing_odd_value():
    values = [1.0, 2.0, 3.0]
    b64 = deflate_base64_floats(values)
    record = f"M|3|MATRIX|EOS|EosScatter|FLOATLE-stream/deflate:base64^{b64}"
    fields = parse_fields(record)
    matrix = decode_matrix(fields)
    assert matrix["points"] == [{"x": 1.0, "y": 2.0}]


def test_decode_matrix_missing_payload():
    fields = parse_fields("M|3|MATRIX|LMNE|LMNEResAbs")
    assert decode_matrix(fields) is None
