"""Tests for Fix 1.3 — N+1 elimination in plan_builder."""
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.mark.asyncio
async def test_single_db_query_for_all_endpoints():
    """
    build_automation_plan must issue exactly ONE Endpoint query regardless
    of how many RAG results are returned.

    build_automation_plan is async and fetches the endpoints for the merged
    RAG results in a single batched query — await db.execute(select(Endpoint)
    .where(Endpoint.id.in_(endpoint_ids))) — not one .query() call per
    result (see app/planner/plan_builder.py).
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

    # db.execute(...) is awaited once; the result's .scalars().unique().all()
    # yields every endpoint fetched by that single roundtrip.
    execute_result = MagicMock()
    execute_result.scalars.return_value.unique.return_value.all.return_value = mock_endpoints
    db = MagicMock()
    db.execute = AsyncMock(return_value=execute_result)

    intent = BusinessIntent(
        instruction="list all resources",
        intent="list resources",
        action="list",
        entities=[],
        confidence=0.9,  # must clear PLAN_MIN_INTENT_CONFIDENCE (0.4) or
        # build_automation_plan returns an empty plan before ever
        # reaching search_rag_context/db.execute.
        requires_bulk_execution=False,
    )

    # search_rag_context is awaited twice (double-query RAG) — both calls
    # return the same 5 results here, so merge_deduplicate collapses them
    # back down to 5 unique endpoints by endpoint_id.
    with patch(
        "app.planner.plan_builder.search_rag_context",
        new=AsyncMock(return_value=(search_results, "ctx")),
    ):
        plan = await build_automation_plan(
            db=db, run_id="run-1", instruction="list all resources", intent=intent
        )

    # Only ONE call to db.execute(select(Endpoint)...) — not one per search result
    assert db.execute.call_count == 1
    assert len(plan.steps) == 5
