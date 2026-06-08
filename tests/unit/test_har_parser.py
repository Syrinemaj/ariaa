"""
Unit tests — HAR parser query param extraction (Section 12.2).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.ingestion.har_parser import parse_har_file


def _write_har(entries: list) -> Path:
    data = {"log": {"entries": entries}}
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".har", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


def _entry(url: str, method: str = "GET", status: int = 200) -> dict:
    return {
        "request": {"method": method, "url": url, "headers": []},
        "response": {"status": status, "content": {}, "headers": []},
    }


class TestQueryParamExtraction:
    def test_query_params_extracted(self):
        path = _write_har([_entry("https://api.example.com/reports?type=monthly&page=1")])
        entries = parse_har_file(path)
        assert entries[0].query_params == {"type": "monthly", "page": "1"}

    def test_no_query_string_yields_empty_dict(self):
        path = _write_har([_entry("https://api.example.com/users")])
        entries = parse_har_file(path)
        assert entries[0].query_params == {}

    def test_path_does_not_include_query_string(self):
        path = _write_har([_entry("https://api.example.com/items?page=2")])
        entries = parse_har_file(path)
        assert "?" not in entries[0].path
        assert entries[0].path == "/items"

    def test_multiple_entries_each_get_own_params(self):
        path = _write_har([
            _entry("https://api.example.com/r?type=monthly"),
            _entry("https://api.example.com/r?type=annual"),
        ])
        entries = parse_har_file(path)
        assert entries[0].query_params["type"] == "monthly"
        assert entries[1].query_params["type"] == "annual"

    def test_blank_value_preserved(self):
        path = _write_har([_entry("https://api.example.com/search?q=")])
        entries = parse_har_file(path)
        assert "q" in entries[0].query_params

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            parse_har_file("/nonexistent/file.har")
