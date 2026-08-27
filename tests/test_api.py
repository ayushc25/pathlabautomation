import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import build_capture, deflate_base64_floats

client = TestClient(app)


def _sample_capture_bytes() -> bytes:
    hist_b64 = deflate_base64_floats([float(i) for i in range(5)])
    records = [
        "H|\\^&|||Instrument^H500|||||Receiver||P|1|20260729120000",
        "P|1||PID123||Doe^Jane||19800101|F",
        "O|1|SAMP001||^^^WBC|||20260729120000",
        "R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F|||20260729120500",
        f"M|1|HISTOGRAM|RBC/PLT|PltAlongRes|FLOATLE-stream/deflate:base64^{hist_b64}",
        "L|1|N",
    ]
    return build_capture(records).encode("utf-8")


def test_health_check():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_decode_endpoint_returns_structured_result():
    capture_bytes = _sample_capture_bytes()
    resp = client.post(
        "/decode",
        files={"file": ("capture.txt", io.BytesIO(capture_bytes), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["patient"]["patient_id"] == "PID123"
    assert body["results"]["WBC"]["value"] == 6.42
    assert body["results"]["WBC"]["device_test_code"] == "WBC"
    assert body["results"]["WBC"]["test_name"] == "White Blood Cells"
    assert "PltAlongRes" in body["histograms"]
    assert "RBC_histogram" in body["images"]


def test_decode_endpoint_rejects_non_txt_file():
    resp = client.post(
        "/decode",
        files={"file": ("capture.bin", io.BytesIO(b"hello"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_decode_endpoint_rejects_empty_file():
    resp = client.post(
        "/decode",
        files={"file": ("capture.txt", io.BytesIO(b""), "text/plain")},
    )
    assert resp.status_code == 400


def test_decode_endpoint_rejects_unparsable_file():
    resp = client.post(
        "/decode",
        files={"file": ("capture.txt", io.BytesIO(b"totally unrelated text content"), "text/plain")},
    )
    assert resp.status_code == 400
