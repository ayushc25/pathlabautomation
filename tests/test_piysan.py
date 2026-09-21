"""Unit tests for Piysan LIS integration."""
from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.database import _connect, _lock, init_databases
from app.services.piysan_service import (
    PiysanClient,
    execute_piysan_request,
    find_latest_decoded_capture,
    get_piysan_settings,
    init_piysan_db,
    load_enriched_bookings,
    load_piysan_bookings,
    load_submission_logs,
    manual_submit_to_piysan,
    save_piysan_bookings,
    save_submission_log,
    trigger_auto_submit,
    update_piysan_settings,
    update_piysan_token,
)

client = TestClient(app)

# Test-local name for the active DB path - reassigned to an isolated temp file by
# the isolated_piysan_db fixture below, so tests never read/write the real app DB.
MAPPING_DB_PATH = None


@pytest.fixture(autouse=True)
def isolated_piysan_db(tmp_path, monkeypatch):
    """Redirects all Piysan DB reads/writes to fresh temp SQLite files for the
    duration of each test, so running the test suite never mutates the real
    application databases (data/mapping_config.sqlite3, data/decoded_results.sqlite3)."""
    test_db_path = tmp_path / "test_mapping_config.sqlite3"
    test_decoded_db_path = tmp_path / "test_decoded_results.sqlite3"

    # app.services.piysan_service.MAPPING_DB_PATH/DECODED_DB_PATH are the names
    # actually used by every query inside piysan_service.py - patch those, not
    # database.py's copies (a `from x import y` binds its own separate name).
    monkeypatch.setattr("app.services.piysan_service.MAPPING_DB_PATH", test_db_path)
    monkeypatch.setattr("app.services.piysan_service.DECODED_DB_PATH", test_decoded_db_path)
    monkeypatch.setattr("app.services.database.MAPPING_DB_PATH", test_db_path)
    monkeypatch.setattr("app.services.database.DECODED_DB_PATH", test_decoded_db_path)
    # This test module also imports/uses MAPPING_DB_PATH directly for assertions.
    monkeypatch.setattr(sys.modules[__name__], "MAPPING_DB_PATH", test_db_path)

    init_databases()  # creates lab_test_master and friends in the temp mapping DB
    init_piysan_db()
    with _lock, _connect(test_db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO piysan_settings (id, base_url, mobile, password, jwt_token, token_expires_at, auto_submit)
            VALUES (1, 'https://staging.piysan.com/', '', '', NULL, NULL, 1)
            """
        )
        conn.commit()
    yield


def test_init_and_settings():
    init_piysan_db()
    settings = get_piysan_settings()
    assert settings["base_url"] == "https://staging.piysan.com/"
    assert settings["auto_submit"] == 1

    # base_url is env-controlled (PIYSAN_BASE_URL) - update_piysan_settings no
    # longer takes it as a parameter; only mobile/password/auto_submit are stored.
    update_piysan_settings("9999999999", "pass123", 0)
    settings = get_piysan_settings()
    assert settings["mobile"] == "9999999999"
    assert settings["password"] == "pass123"
    assert settings["auto_submit"] == 0


@patch("httpx.Client.post")
def test_client_login(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"token": "test-jwt-token-123"}
    mock_post.return_value = mock_response

    cli = PiysanClient("https://staging.piysan.com", "9876543210", "mypass")
    token = cli.login()
    assert token == "test-jwt-token-123"
    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "https://staging.piysan.com/api/lis/login"
    assert mock_post.call_args[1]["json"] == {"mobile": "9876543210", "password": "mypass"}


@patch("httpx.Client.get")
def test_client_get_bookings(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"reference_no": "REF001", "patient": {"name": "Patient One"}}
    ]
    mock_get.return_value = mock_response

    cli = PiysanClient("https://staging.piysan.com")
    bookings = cli.get_bookings("mytoken", limit=10, offset=0)
    assert len(bookings) == 1
    assert bookings[0]["reference_no"] == "REF001"
    mock_get.assert_called_once()
    assert "Authorization" in mock_get.call_args[1]["headers"]


@patch("httpx.Client.post")
def test_client_submit_report(mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success"}
    mock_post.return_value = mock_response

    cli = PiysanClient("https://staging.piysan.com")
    res = cli.submit_report("mytoken", "REF001", [{"test_id": 1, "value": 10.5}])
    assert res["status"] == "success"
    mock_post.assert_called_once()
    assert mock_post.call_args[0][0] == "https://staging.piysan.com/api/lis/submit_report"


@patch("app.services.piysan_service.PiysanClient.login")
@patch("app.services.piysan_service.PiysanClient.get_bookings")
def test_execute_piysan_request_auto_login(mock_bookings, mock_login):
    update_piysan_settings("9876543210", "pass", 1)
    mock_login.return_value = "new-token-abc"
    mock_bookings.return_value = [{"reference_no": "REF001"}]

    res = execute_piysan_request("get_bookings", limit=5)
    assert res == [{"reference_no": "REF001"}]
    mock_login.assert_called_once()
    mock_bookings.assert_called_once_with("new-token-abc", limit=5)

    # Secondary call should reuse token without logging in again
    res2 = execute_piysan_request("get_bookings", limit=5)
    assert res2 == [{"reference_no": "REF001"}]
    assert mock_login.call_count == 1 # still 1


@patch("app.services.piysan_service.PiysanClient.login")
@patch("app.services.piysan_service.PiysanClient.get_bookings")
def test_execute_piysan_request_self_healing_401(mock_bookings, mock_login):
    update_piysan_settings("9876543210", "pass", 1)
    update_piysan_token("old-bad-token", "2030-01-01T12:00:00") # future expire

    # First call to get_bookings raises 401, second succeeds
    response_401 = httpx.Response(401, request=httpx.Request("GET", "http://test"))
    mock_bookings.side_effect = [
        httpx.HTTPStatusError("Unauthorized", request=response_401.request, response=response_401),
        [{"reference_no": "REF001"}]
    ]
    mock_login.return_value = "refreshed-token"

    res = execute_piysan_request("get_bookings")
    assert res == [{"reference_no": "REF001"}]
    assert mock_login.call_count == 1
    assert mock_bookings.call_count == 2
    mock_bookings.assert_any_call("old-bad-token")
    mock_bookings.assert_any_call("refreshed-token")


def test_save_and_load_bookings():
    bookings = [
        {
            "reference_no": "REF_A",
            "patient": {"name": "Jane Doe", "id": "PID999"},
            "machines": [
                {
                    "machine_id": "001",
                    "tests": [
                        {"test_id": 555, "test_name": "Test WBC", "test_category_name": "CBC"}
                    ]
                }
            ]
        }
    ]
    save_piysan_bookings(bookings)
    loaded = load_piysan_bookings()
    assert len(loaded) == 1
    assert loaded[0]["reference_no"] == "REF_A"
    assert loaded[0]["patient_name"] == "Jane Doe"
    assert loaded[0]["patient_id"] == "PID999"

    # Verify lab_test_master auto-import
    with _lock, _connect(MAPPING_DB_PATH) as conn:
        row = conn.execute("SELECT * FROM lab_test_master WHERE test_id = '555'").fetchone()
        assert row is not None
        assert row["test_name"] == "Test WBC"


def test_submission_logging():
    save_submission_log("REF_1", 12, {"key": "val"}, {"status": "ok"}, "success", "")
    logs = load_submission_logs(limit=10)
    assert len(logs) == 1
    assert logs[0]["reference_no"] == "REF_1"
    assert logs[0]["status"] == "success"
    assert "val" in logs[0]["payload"]
    assert "ok" in logs[0]["response"]


@patch("app.services.piysan_service.execute_piysan_request")
def test_trigger_auto_submit(mock_execute):
    mock_execute.return_value = {"status": "accepted"}
    
    # Save booking to cache
    booking = {
        "reference_no": "REF_AUTO",
        "patient": {"name": "Auto patient"},
        "machines": [{"tests": [{"test_id": 901, "test_name": "Total WBC"}]}]
    }
    save_piysan_bookings([booking])

    report = {
        "order": {"sample_id": "REF_AUTO"},
        "results": {
            "901": {"value": 15.2, "test_name": "Total WBC"}
        }
    }
    
    # Enable auto_submit in settings
    update_piysan_settings("9876543210", "pass", 1)

    trigger_auto_submit(99, report)
    mock_execute.assert_called_once()
    assert mock_execute.call_args[0][0] == "submit_report"
    assert mock_execute.call_args[0][1] == "REF_AUTO"
    assert mock_execute.call_args[0][2] == {"901": 15.2}

    # Verify submission log was created
    logs = load_submission_logs()
    assert len(logs) == 1
    assert logs[0]["reference_no"] == "REF_AUTO"
    assert logs[0]["status"] == "success"


@patch("app.services.piysan_service.execute_piysan_request")
def test_trigger_auto_submit_when_booking_has_no_test_id(mock_execute):
    """Real Piysan get_bookings responses only return test_name (no test_id) per
    test. Auto-submit must still work by order-level match (reference_no has a
    known booking + has decoded numeric results) rather than per-test test_id
    cross-checking, which would otherwise always find zero matches."""
    mock_execute.return_value = {"status": "accepted"}

    booking = {
        "reference_no": "REF_NO_TESTID",
        "patient": {"first_name": "No", "last_name": "TestId"},
        "machines": [{"machine_id": "001", "tests": [{"test_name": "Hematocrit", "machine_id": "001"}]}],
    }
    save_piysan_bookings([booking])

    report = {
        "order": {"sample_id": "REF_NO_TESTID"},
        "results": {"901": {"value": 42.0, "test_name": "Hematocrit"}},
    }

    update_piysan_settings("9876543210", "pass", 1)

    trigger_auto_submit(100, report)
    mock_execute.assert_called_once()
    assert mock_execute.call_args[0][1] == "REF_NO_TESTID"
    assert mock_execute.call_args[0][2] == {"901": 42.0}

    logs = load_submission_logs()
    assert logs[0]["reference_no"] == "REF_NO_TESTID"
    assert logs[0]["status"] == "success"


@patch("app.services.piysan_service.execute_piysan_request")
def test_manual_submit_when_booking_has_no_test_id(mock_execute):
    """Same order-level-match guarantee for the manual 'Push Results' path."""
    mock_execute.return_value = {"status": "accepted"}

    booking = {
        "reference_no": "REF_MANUAL_NO_TESTID",
        "patient": {"first_name": "Manual", "last_name": "Push"},
        "machines": [{"machine_id": "001", "tests": [{"test_name": "WBC", "machine_id": "001"}]}],
    }
    save_piysan_bookings([booking])

    from app.services.database import save_decoded_capture

    save_decoded_capture(
        "test",
        {"order": {"sample_id": "REF_MANUAL_NO_TESTID"}, "results": {"501": {"value": 7.7, "test_name": "WBC"}}},
    )

    response = manual_submit_to_piysan("REF_MANUAL_NO_TESTID")
    assert response == {"status": "accepted"}
    mock_execute.assert_called_once_with("submit_report", "REF_MANUAL_NO_TESTID", {"501": 7.7})


def test_manual_submit_rejects_order_not_in_bookings():
    """If reference_no doesn't correspond to any booking we actually received
    from Piysan, submission must be refused rather than pushing blind."""
    from app.services.database import save_decoded_capture

    save_decoded_capture(
        "test",
        {"order": {"sample_id": "REF_UNKNOWN_ORDER"}, "results": {"501": {"value": 7.7}}},
    )

    with pytest.raises(ValueError, match="not found among bookings"):
        manual_submit_to_piysan("REF_UNKNOWN_ORDER")


def test_auth_required_endpoints():
    # Attempting to get /piysan without auth redirects to /login
    resp = client.get("/piysan", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")

    # API endpoints return 401 when not authed
    resp = client.post("/piysan/test-connection")
    assert resp.status_code == 401


@patch("app.services.piysan_service.PiysanClient.login")
def test_login_via_piysan_api(mock_login):
    mock_login.return_value = "jwt-token-via-login-screen"

    resp = client.post("/login", data={"username": "9876543210", "password": "mypassword"})
    assert resp.status_code == 200
    assert resp.json() == {"status": "success", "redirect": "/dashboard"}

    # Settings should be updated in SQLite
    settings = get_piysan_settings()
    assert settings["mobile"] == "9876543210"
    assert settings["password"] == "mypassword"
    assert settings["jwt_token"] == "jwt-token-via-login-screen"


def test_enriched_bookings_prefill():
    bookings = [
        {
            "reference_no": "REF_PREFILL",
            "patient": {"name": "Prefill Patient", "id": "PID777", "dob": "1995-05-15", "gender": "F"},
            "machines": [
                {
                    "machine_id": "001",
                    "tests": [
                        {"test_id": 901, "test_name": "WBC", "test_category_name": "CBC"}
                    ]
                }
            ]
        }
    ]
    save_piysan_bookings(bookings)
    enriched = load_enriched_bookings()
    
    # Search for our booking
    matched = [b for b in enriched if b["reference_no"] == "REF_PREFILL"]
    assert len(matched) == 1
    assert matched[0]["patient_name"] == "Prefill Patient"
    assert matched[0]["dob_str"] == "1995-05-15"
    assert matched[0]["gender_str"] == "F"
    assert matched[0]["test_ids_str"] == "901"
    assert matched[0]["is_skipped"] is False


def test_toggle_skip_booking():
    from app.services.piysan_service import toggle_skip_booking
    booking = {
        "reference_no": "REF_SKIP_TEST",
        "patient": {"first_name": "Skip", "last_name": "Me"},
        "machines": [],
    }
    save_piysan_bookings([booking])
    
    # Toggle to skipped
    new_state = toggle_skip_booking("REF_SKIP_TEST")
    assert new_state is True
    
    enriched = load_enriched_bookings()
    matched = [b for b in enriched if b["reference_no"] == "REF_SKIP_TEST"]
    assert len(matched) == 1
    assert matched[0]["is_skipped"] is True
    
    # Toggle back to unskipped
    unskipped = toggle_skip_booking("REF_SKIP_TEST", is_skipped=False)
    assert unskipped is False



