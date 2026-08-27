from app.services.record_parser import parse_fields
from app.services.test_code_lookup import all_test_codes, resolve_test_name
from app.services.result_decoder import decode_results, parse_result_record


def test_parse_result_record_extracts_parameter_and_value():
    fields = parse_fields("R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F|||20260729120500")
    parsed = parse_result_record(fields)
    assert parsed["parameter"] == "WBC"
    assert parsed["entry"]["value"] == 6.42
    assert parsed["entry"]["unit"] == "10^3/uL"
    assert parsed["entry"]["status"] == "F"
    assert parsed["entry"]["timestamp"] == "20260729120500"


def test_parse_result_record_reference_range_and_flags():
    fields = parse_fields("R|2|^^^RBC|4.81|10*6/uL|4.20-6.10|H\\HH||F")
    parsed = parse_result_record(fields)
    assert parsed["entry"]["reference_range"] == {"low": 4.2, "high": 6.1}
    assert parsed["entry"]["flags"] == ["H", "HH"]


def test_parse_result_record_returns_none_when_no_parameter():
    fields = parse_fields("R|1|^^^|6.42|units")
    assert parse_result_record(fields) is None


def test_decode_results_builds_flat_dict_and_skips_bad_records():
    records = [
        parse_fields("R|1|^^^WBC|6.42|10^3/uL|4.00-10.00|N||F"),
        parse_fields("R|2|^^^RBC|4.81|10^6/uL|4.20-6.10|N||F"),
        parse_fields("R|3|^^^|bad"),  # unresolvable parameter, should be skipped
    ]
    results = decode_results(records)
    assert set(results.keys()) == {"WBC", "RBC"}
    assert results["WBC"]["value"] == 6.42
    assert results["RBC"]["value"] == 4.81


def test_test_code_lookup_resolves_known_codes():
    assert resolve_test_name("6690-2") == "White Blood Cells"
    assert resolve_test_name("71695-1") == "Immature Granulocytic cells percentage"
    assert resolve_test_name("does-not-exist") is None


def test_test_code_lookup_contains_expected_catalog():
    catalog = all_test_codes()
    assert catalog["789-8"]["name"] == "Red Blood Cells"
    assert catalog["789-8"]["panel"] == "CBC"
    assert catalog["82477-1"]["panel"] == "ESR"
