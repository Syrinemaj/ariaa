import pytest
from fastapi import HTTPException

from app.security.ssrf_guard import validate_target_url


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://10.0.0.1",
        "http://192.168.1.1",
        "ftp://example.com",
    ],
)
def test_ssrf_guard_blocks_dangerous_urls(url):
    with pytest.raises(HTTPException):
        validate_target_url(url)
