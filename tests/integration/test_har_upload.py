from unittest.mock import patch
from app.ingestion.models import TrafficEntry


def make_entry(method="GET", path="/api/users", status=200):
    return TrafficEntry(
        method=method,
        url=f"https://api.example.com{path}",
        path=path,
        status=status,
        is_api_candidate=True,
        decision="kept",
        heuristic_score=0.8,
    )


def test_rejects_non_har_file(client):
    response = client.post(
        "/upload/har",
        files={"file": ("data.json", b"{}", "application/json")},
    )
    assert response.status_code == 400
    assert "har" in response.json()["detail"].lower()


def test_rejects_missing_filename(client):
    response = client.post(
        "/upload/har",
        files={"file": ("", b"{}", "application/json")},
    )
    assert response.status_code >= 400


def test_upload_har_returns_entries(client, har_bytes):
    fake_entries = [make_entry("GET", "/api/users", 200)]

    with patch("app.api.upload.process_har_file", return_value=fake_entries):
        response = client.post(
            "/upload/har",
            files={"file": ("traffic.har", har_bytes, "application/json")},
        )

    assert response.status_code == 200
    data = response.json()
    assert "file_id" in data
    assert data["total_entries"] == 1
    assert data["entries"][0]["method"] == "GET"
    assert data["entries"][0]["path"] == "/api/users"


def test_upload_har_empty_pipeline(client, har_bytes):
    with patch("app.api.upload.process_har_file", return_value=[]):
        response = client.post(
            "/upload/har",
            files={"file": ("empty.har", har_bytes, "application/json")},
        )

    assert response.status_code == 200
    assert response.json()["total_entries"] == 0
