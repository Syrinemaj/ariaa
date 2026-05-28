"""Tests for Fix 1.3 — N+1 elimination in plan_builder."""
from unittest.mock import MagicMock, patch

import pytest

from app.planner.models import BusinessIntent
from app.planner.plan_builder import build_automation_plan


def _make_mock_endpoint(eid: str, method: str = "GET", path: str = "/test") -> MagicMock:
    ep = MagicMock()
    ep.id = eid
    ep.method = method
    ep.path = path
    ep.canonical_key = f"org:{method} {path}"
    ep.business_domain = "test"
    ep.business_action = "read"
    ep.metadata_json = {}
    schema = MagicMock()
    schema.request_schema = None
    schema.response_schema = None
    schema.auth_required = False
    ep.schema = schema
    return ep


def test_single_db_query_for_all_endpoints():
    """
    build_automation_plan must issue exactly ONE Endpoint query regardless
    of how many RAG results are returned.
    """
    from app.rag.models import EndpointSearchResult

    search_results = [
        EndpointSearchResult(
            endpoint_id=f"ep-{i}",
            method="GET",
            path=f"/resource/{i}",
            canonical_key=f"org:GET /resource/{i}",
            score=0.9,
            embedding_text="",
            metadata={},
        )
        for i in range(5)
    ]

    mock_endpoints = [_make_mock_endpoint(f"ep-{i}", path=f"/resource/{i}") for i in range(5)]

    db = MagicMock()
    # Simulate the chained query: .options().filter().all()
    query_chain = MagicMock()
    query_chain.options.return_value = query_chain
    query_chain.filter.return_value = query_chain
    query_chain.all.return_value = mock_endpoints
    db.query.return_value = query_chain

    intent = BusinessIntent(
        intent="list resources",
        action="list",
        entities=[],
        requires_bulk_execution=False,
    )

    with patch("app.planner.plan_builder.search_rag_context", return_value=(search_results, "ctx")):
        plan = build_automation_plan(db=db, run_id="run-1", instruction="list all resources", intent=intent)

    # Only ONE call to db.query(Endpoint) — not one per search result
    assert db.query.call_count == 1
    assert len(plan.steps) == 5
