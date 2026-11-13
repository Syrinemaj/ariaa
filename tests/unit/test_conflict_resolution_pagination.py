"""Duplicate-conflict lookup must find the existing record beyond the first list page."""
import asyncio

import httpx

from app.bulk_execution.conflict_resolution import find_existing_record

EMPLOYEES = [{"id": i, "email": f"user{i}@example.com"} for i in range(1, 46)]  # 45 items


def _paginated_handler(request: httpx.Request) -> httpx.Response:
    page = int(request.url.params.get("page", 1))
    size = int(request.url.params.get("page_size", 20))
    start = (page - 1) * size
    return httpx.Response(200, json={
        "items": EMPLOYEES[start:start + size], "total": len(EMPLOYEES), "page": page, "page_size": size,
    })


def _lookup(email, handler=_paginated_handler):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await find_existing_record(
                client, "http://target", {}, "/api/employees", {"email": email, "full_name": "X"},
            )
    return asyncio.run(run())


def test_record_on_first_page_is_found():
    assert _lookup("user3@example.com")["id"] == 3


def test_record_on_a_later_page_is_found():
    assert _lookup("user44@example.com")["id"] == 44


def test_unknown_record_returns_none_after_reading_all_pages():
    assert _lookup("nobody@example.com") is None


def test_plain_list_response_still_works():
    def handler(request):
        return httpx.Response(200, json=EMPLOYEES)
    assert _lookup("user40@example.com", handler)["id"] == 40
