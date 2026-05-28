import pytest
from app.ingestion.heuristic_filter import compute_heuristic_score, has_api_hint, has_json_content
from app.ingestion.models import TrafficEntry


def make_entry(**kwargs):
    defaults = {
        "method": "GET",
        "url": "https://example.com/page",
        "path": "/page",
        "status": 200,
        "mime_type": "text/html",
        "request_headers": {},
        "response_headers": {},
    }
    defaults.update(kwargs)
    return TrafficEntry(**defaults)


class TestHasApiHint:
    def test_api_path(self):
        assert has_api_hint("/api/users") is True

    def test_v1_path(self):
        assert has_api_hint("/v1/products") is True

    def test_graphql_path(self):
        assert has_api_hint("/graphql") is True

    def test_plain_path(self):
        assert has_api_hint("/about") is False

    def test_rest_path(self):
        assert has_api_hint("/rest/items") is True


class TestHasJsonContent:
    def test_response_header(self):
        entry = make_entry(response_headers={"content-type": "application/json"})
        assert has_json_content(entry) is True

    def test_mime_type(self):
        entry = make_entry(mime_type="application/json")
        assert has_json_content(entry) is True

    def test_dict_body(self):
        entry = make_entry(request_body={"key": "value"})
        assert has_json_content(entry) is True

    def test_no_json(self):
        entry = make_entry(mime_type="text/html")
        assert has_json_content(entry) is False


class TestComputeHeuristicScore:
    def test_post_json_api_path(self):
        entry = make_entry(
            method="POST",
            path="/api/users",
            status=201,
            response_headers={"content-type": "application/json"},
        )
        score = compute_heuristic_score(entry)
        assert score >= 0.9

    def test_get_html_no_hint(self):
        entry = make_entry(method="GET", path="/about", status=200)
        score = compute_heuristic_score(entry)
        assert score <= 0.2

    def test_score_capped_at_1(self):
        entry = make_entry(
            method="DELETE",
            path="/api/v1/items",
            status=200,
            mime_type="application/json",
            response_headers={"content-type": "application/json"},
        )
        score = compute_heuristic_score(entry)
        assert score <= 1.0

    def test_non_2xx_no_status_bonus(self):
        entry = make_entry(method="GET", path="/api/test", status=500)
        score_500 = compute_heuristic_score(entry)
        entry_200 = make_entry(method="GET", path="/api/test", status=200)
        score_200 = compute_heuristic_score(entry_200)
        assert score_200 > score_500
