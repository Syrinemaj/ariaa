"""
Unit tests — QueryParamProfile + fingerprinting (Section 12.2).
"""
from __future__ import annotations

from app.ingestion.models import TrafficEntry
from app.normalization.query_params import (
    QueryParamProfile,
    build_endpoint_fingerprint,
    classify_query_params,
)


def _entry(query_params: dict) -> TrafficEntry:
    return TrafficEntry(
        method="GET",
        url="https://api.example.com/reports",
        path="/reports",
        query_params=query_params,
    )


# ── classify_query_params ──────────────────────────────────────────────────────

class TestClassifyQueryParams:
    def test_single_value_is_constant(self):
        entries = [_entry({"format": "json"}), _entry({"format": "json"})]
        profiles = classify_query_params(entries, "GET /reports")
        assert profiles["format"].param_type == "constant"
        assert profiles["format"].observed_values == ["json"]

    def test_multiple_values_is_variable(self):
        entries = [_entry({"type": "monthly"}), _entry({"type": "annual"})]
        profiles = classify_query_params(entries, "GET /reports")
        assert profiles["type"].param_type == "variable"
        assert set(profiles["type"].observed_values) == {"monthly", "annual"}

    def test_boolean_values_classified_as_flag(self):
        entries = [_entry({"active": "true"}), _entry({"active": "false"})]
        profiles = classify_query_params(entries, "GET /users")
        assert profiles["active"].param_type == "flag"

    def test_zero_one_classified_as_flag(self):
        entries = [_entry({"enabled": "1"}), _entry({"enabled": "0"})]
        profiles = classify_query_params(entries, "GET /features")
        assert profiles["enabled"].param_type == "flag"

    def test_no_query_params_returns_empty(self):
        entries = [_entry({})]
        profiles = classify_query_params(entries, "GET /items")
        assert profiles == {}

    def test_mixed_entries_deduplicated(self):
        entries = [_entry({"page": "1"}), _entry({"page": "1"}), _entry({"page": "2"})]
        profiles = classify_query_params(entries, "GET /items")
        assert profiles["page"].param_type == "variable"
        assert len(profiles["page"].observed_values) == 2


# ── build_endpoint_fingerprint ────────────────────────────────────────────────

class TestBuildFingerprint:
    def test_no_params_returns_method_path(self):
        fp = build_endpoint_fingerprint("GET", "/items", {})
        assert fp == "GET /items"

    def test_variable_param_uses_placeholder(self):
        profiles = {"type": QueryParamProfile("type", "variable", ["monthly", "annual"])}
        fp = build_endpoint_fingerprint("GET", "/reports", profiles)
        assert fp == "GET /reports?type={type}"

    def test_constant_param_hardcoded(self):
        profiles = {"format": QueryParamProfile("format", "constant", ["json"])}
        fp = build_endpoint_fingerprint("GET", "/data", profiles)
        assert fp == "GET /data?format=json"

    def test_flag_param_uses_placeholder(self):
        profiles = {"active": QueryParamProfile("active", "flag", ["true", "false"])}
        fp = build_endpoint_fingerprint("GET", "/users", profiles)
        assert fp == "GET /users?active={active}"

    def test_multiple_params_sorted_alphabetically(self):
        profiles = {
            "page": QueryParamProfile("page", "variable", ["1", "2"]),
            "format": QueryParamProfile("format", "constant", ["json"]),
        }
        fp = build_endpoint_fingerprint("GET", "/items", profiles)
        # sorted: format before page
        assert fp == "GET /items?format=json&page={page}"

    def test_distinct_reports_get_distinct_fingerprints(self):
        p1 = {"type": QueryParamProfile("type", "constant", ["monthly"])}
        p2 = {"type": QueryParamProfile("type", "constant", ["annual"])}
        fp1 = build_endpoint_fingerprint("GET", "/reports", p1)
        fp2 = build_endpoint_fingerprint("GET", "/reports", p2)
        assert fp1 != fp2
