"""Tests for Phase 2E — build_automation_plan() (app/planner/plan_builder.py)
consuming the full dict now returned by generate_plan_selection()
(app/planner/plan_generator.py), instead of just a list of canonical keys.

Note: tests/unit/test_plan_builder_n1.py is a pre-existing, already-broken
test for an older SYNC version of build_automation_plan() (db.query(...),
no await) — unrelated to this change, not touched here.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import settings
from app.models.workflow import WorkflowModel
from app.planner.models import BusinessIntent
from app.planner.plan_builder import build_automation_plan
from app.rag.models import EndpointSearchResult


def _make_mock_endpoint(eid, method="POST", path="/employees"):
    ep = MagicMock()
    ep.id = eid
    ep.method = method
    ep.path = path
    ep.canonical_key = f"{method} {path}"
    ep.business_domain = "hr"
    ep.business_action = "create"
    schema = MagicMock()
    schema.request_schema = None
    schema.response_schema = None
    schema.auth_required = False
    ep.schema = schema
    return ep


def _make_db(endpoints):
    db = MagicMock()
    execute_result = MagicMock()
    execute_result.scalars.return_value.unique.return_value.all.return_value = endpoints
    db.execute = AsyncMock(return_value=execute_result)
    return db


def _make_intent():
    return BusinessIntent(
        instruction="Crée un employé", intent="create employee",
        action="create", entities=["employee"], confidence=0.9,
    )


def _search_results():
    return [
        EndpointSearchResult(
            endpoint_id="ep-1", method="POST", path="/employees",
            canonical_key="POST /employees", score=0.9, embedding_text="", metadata={},
        ),
        EndpointSearchResult(
            endpoint_id="ep-2", method="GET", path="/products",
            canonical_key="GET /products", score=0.85, embedding_text="", metadata={},
        ),
    ]


class TestBuildAutomationPlanWithLLMSelection:
    @pytest.mark.asyncio
    async def test_full_dict_filters_steps_and_populates_metadata(self):
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = _make_intent()

        plan_result = {
            "selected_canonical_keys": ["POST /employees"],
            "steps": [{
                "order": 1, "canonical_key": "POST /employees", "action": "create",
                "required": True, "depends_on": [], "loop": None, "field_mapping": {},
            }],
            "reasoning": "only employee creation matches",
            "missing_endpoints": [],
            "confidence": 0.88,
        }

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=plan_result,
        ) as mock_gen:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(),
            )

        assert len(plan.steps) == 1
        assert plan.steps[0].canonical_key == "POST /employees"
        assert plan.metadata["reasoning"] == "only employee creation matches"
        assert plan.metadata["missing_endpoints"] == []
        assert plan.metadata["plan_confidence"] == 0.88
        assert plan.metadata["steps_detail"] == plan_result["steps"]

        mock_gen.assert_called_once()
        _, kwargs = mock_gen.call_args
        assert kwargs["intent"] is intent

    @pytest.mark.asyncio
    async def test_field_mapping_populated_and_survives_dependency_sort(self):
        # field_mapping is set on the PlanStep BEFORE the
        # detect_schema_dependencies/topological_sort_steps round-trip
        # (model_dump() -> dict -> PlanStep(**d)) — this specifically checks
        # it isn't silently dropped by that reconstruction.
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = _make_intent()

        plan_result = {
            "selected_canonical_keys": ["POST /employees"],
            "steps": [{
                "order": 1, "canonical_key": "POST /employees", "action": "create",
                "required": True, "depends_on": [], "loop": "csv_rows",
                "field_mapping": {"prénom": "first_name", "type_contrat": None},
            }],
            "reasoning": "r", "missing_endpoints": [], "confidence": 0.9,
        }

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch("app.planner.plan_builder.generate_plan_selection", return_value=plan_result):
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(),
            )

        assert plan.steps[0].field_mapping == {"prénom": "first_name", "type_contrat": None}

    @pytest.mark.asyncio
    async def test_field_mapping_defaults_empty_without_llm(self):
        db = _make_db([
            _make_mock_endpoint("ep-1"),
            _make_mock_endpoint("ep-2", method="GET", path="/products"),
        ])
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch("app.planner.plan_builder.generate_plan_selection") as mock_gen:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=None,
            )

        mock_gen.assert_not_called()
        assert all(step.field_mapping == {} for step in plan.steps)

    @pytest.mark.asyncio
    async def test_none_falls_back_to_unfiltered_rag_results(self):
        db = _make_db([
            _make_mock_endpoint("ep-1"),
            _make_mock_endpoint("ep-2", method="GET", path="/products"),
        ])
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch("app.planner.plan_builder.generate_plan_selection", return_value=None):
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(),
            )

        assert len(plan.steps) == 2  # unfiltered — both RAG results kept
        assert "reasoning" not in plan.metadata
        assert "plan_confidence" not in plan.metadata

    @pytest.mark.asyncio
    async def test_no_ai_client_never_calls_generate_plan_selection(self):
        db = _make_db([
            _make_mock_endpoint("ep-1"),
            _make_mock_endpoint("ep-2", method="GET", path="/products"),
        ])
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch("app.planner.plan_builder.generate_plan_selection") as mock_gen:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=None,
            )

        mock_gen.assert_not_called()
        assert len(plan.steps) == 2


class TestBuildAutomationPlanDoubleQueryRAG:
    @pytest.mark.asyncio
    async def test_two_queries_issued_and_results_merged_deduplicated(self):
        # query_1 (direct intent) returns ep-1 with a low score, query_2
        # (implicit dependencies) returns ep-1 again with a higher score plus
        # a new ep-3 — merge_deduplicate() must keep ep-1's higher score and
        # not duplicate it, while still including ep-3.
        db = _make_db([
            _make_mock_endpoint("ep-1"),
            _make_mock_endpoint("ep-2", method="GET", path="/products"),
            _make_mock_endpoint("ep-3", method="POST", path="/employees/salary"),
        ])
        intent = _make_intent()

        results_1 = [
            EndpointSearchResult(
                endpoint_id="ep-1", method="POST", path="/employees",
                canonical_key="POST /employees", score=0.5, embedding_text="", metadata={},
            ),
            EndpointSearchResult(
                endpoint_id="ep-2", method="GET", path="/products",
                canonical_key="GET /products", score=0.4, embedding_text="", metadata={},
            ),
        ]
        results_2 = [
            EndpointSearchResult(
                endpoint_id="ep-1", method="POST", path="/employees",
                canonical_key="POST /employees", score=0.95, embedding_text="", metadata={},
            ),
            EndpointSearchResult(
                endpoint_id="ep-3", method="POST", path="/employees/salary",
                canonical_key="POST /employees/salary", score=0.7, embedding_text="", metadata={},
            ),
        ]

        mock_search = AsyncMock(side_effect=[(results_1, "ctx1"), (results_2, "ctx2")])

        with patch(
            "app.planner.plan_builder.search_rag_context", new=mock_search,
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=None,
        ):
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(),
            )

        assert mock_search.call_count == 2
        first_kwargs = mock_search.call_args_list[0].kwargs
        second_kwargs = mock_search.call_args_list[1].kwargs
        assert first_kwargs["top_k"] == 5
        assert second_kwargs["top_k"] == 3
        assert "setup configuration assign notify contract" in second_kwargs["query"]

        # merged/deduplicated: ep-1 (best score 0.95), ep-3 (0.7), ep-2 (0.4)
        assert len(plan.steps) == 3
        canonical_keys = [s.canonical_key for s in plan.steps]
        assert canonical_keys.count("POST /employees") == 1
        assert "POST /employees/salary" in canonical_keys
        assert "GET /products" in canonical_keys


class TestBuildAutomationPlanWorkflowLookup:
    def _make_db_with_workflow(self, endpoints, workflow=None):
        db = MagicMock()
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow
        endpoint_result = MagicMock()
        endpoint_result.scalars.return_value.unique.return_value.all.return_value = endpoints
        db.execute = AsyncMock(side_effect=[workflow_result, endpoint_result])
        return db

    @pytest.mark.asyncio
    async def test_lookup_runs_and_result_passed_to_generate_plan_selection(self):
        found_workflow = MagicMock(spec=WorkflowModel)
        db = self._make_db_with_workflow([_make_mock_endpoint("ep-1")], workflow=found_workflow)
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=None,
        ) as mock_gen:
            await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(), org_id="org-1",
            )

        assert db.execute.call_count == 2  # workflow lookup + endpoint batch load
        _, kwargs = mock_gen.call_args
        assert kwargs["existing_workflow"] is found_workflow

    @pytest.mark.asyncio
    async def test_lookup_skipped_when_org_id_is_none(self):
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=None,
        ) as mock_gen:
            await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(), org_id=None,
            )

        _, kwargs = mock_gen.call_args
        assert kwargs["existing_workflow"] is None

    @pytest.mark.asyncio
    async def test_lookup_skipped_when_caller_already_passed_existing_workflow(self):
        caller_workflow = MagicMock(spec=WorkflowModel)
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = _make_intent()

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=None,
        ) as mock_gen:
            await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(), org_id="org-1",
                existing_workflow=caller_workflow,
            )

        # only the endpoint batch load — no workflow lookup query issued
        assert db.execute.call_count == 1
        _, kwargs = mock_gen.call_args
        assert kwargs["existing_workflow"] is caller_workflow


class TestPhase5FieldMappingEndToEndWithWorkflowLookup:
    @pytest.mark.asyncio
    async def test_field_mapping_populated_when_existing_workflow_comes_from_auto_lookup(self):
        # Phase 5 confirmation: the field_mapping wiring built in 2F needs no
        # changes now that existing_workflow can come from the Phase 4 auto
        # lookup instead of only being caller-supplied — this exercises both
        # together (lookup finds a workflow -> passed into
        # generate_plan_selection -> its steps_detail carries field_mapping
        # -> field_mapping lands on the right PlanStep).
        found_workflow = MagicMock(spec=WorkflowModel)
        db = self._db_with_workflow_then_endpoints(
            workflow=found_workflow, endpoints=[_make_mock_endpoint("ep-1")],
        )
        intent = _make_intent()

        plan_result = {
            "selected_canonical_keys": ["POST /employees"],
            "steps": [{
                "order": 1, "canonical_key": "POST /employees", "action": "create",
                "required": True, "depends_on": [], "loop": "csv_rows",
                "field_mapping": {"prénom": "first_name"},
            }],
            "reasoning": "matched known workflow", "missing_endpoints": [], "confidence": 0.92,
        }

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ), patch(
            "app.planner.plan_builder.generate_plan_selection", return_value=plan_result,
        ) as mock_gen:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=MagicMock(), org_id="org-1",
            )

        _, kwargs = mock_gen.call_args
        assert kwargs["existing_workflow"] is found_workflow
        assert plan.steps[0].field_mapping == {"prénom": "first_name"}

    @staticmethod
    def _db_with_workflow_then_endpoints(workflow, endpoints):
        db = MagicMock()
        workflow_result = MagicMock()
        workflow_result.scalar_one_or_none.return_value = workflow
        endpoint_result = MagicMock()
        endpoint_result.scalars.return_value.unique.return_value.all.return_value = endpoints
        db.execute = AsyncMock(side_effect=[workflow_result, endpoint_result])
        return db


class TestBuildAutomationPlanConfidenceGate:
    """FIX 1 (post-Phase 8 finding) — build_automation_plan() must reject a
    low-confidence intent before calling search_rag_context(), instead of
    running RAG + generate_plan_selection() for an instruction that
    app/api/automation.py:310 rejects anyway once it sees the same
    confidence. Reuses settings.PLAN_MIN_INTENT_CONFIDENCE (already 0.4,
    already enforced there) rather than a second, separate threshold."""

    @pytest.mark.asyncio
    async def test_low_confidence_skips_rag_and_returns_rejected_plan(self):
        db = MagicMock()
        intent = BusinessIntent(
            instruction="bonjour", intent="greeting", action="other",
            entities=[], confidence=0.1, reason="INSTRUCTION_UNCLEAR",
        )

        with patch(
            "app.planner.plan_builder.search_rag_context", new=AsyncMock(),
        ) as mock_search:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="bonjour",
                intent=intent, ai_client=MagicMock(),
            )

        mock_search.assert_not_called()
        db.execute.assert_not_called()
        assert plan.steps == []
        assert plan.workflow_name == "rejected_low_confidence"
        assert plan.requires_approval is False
        assert plan.metadata["skip_reason"] == "intent_confidence_too_low"

    @pytest.mark.asyncio
    async def test_confidence_at_threshold_is_not_rejected(self):
        # settings.PLAN_MIN_INTENT_CONFIDENCE == 0.4 — a confidence exactly
        # at the threshold must pass through (strict "<", not "<=").
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = BusinessIntent(
            instruction="Crée un employé", intent="create", action="create",
            entities=["employee"], confidence=settings.PLAN_MIN_INTENT_CONFIDENCE,
        )

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ) as mock_search:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=None,
            )

        mock_search.assert_called()
        assert plan.workflow_name != "rejected_low_confidence"

    @pytest.mark.asyncio
    async def test_high_confidence_proceeds_normally(self):
        db = _make_db([_make_mock_endpoint("ep-1")])
        intent = _make_intent()  # confidence=0.9

        with patch(
            "app.planner.plan_builder.search_rag_context",
            new=AsyncMock(return_value=(_search_results(), "ctx")),
        ) as mock_search:
            plan = await build_automation_plan(
                db=db, run_id="run-1", instruction="Crée un employé",
                intent=intent, ai_client=None,
            )

        mock_search.assert_called()
        assert plan.workflow_name != "rejected_low_confidence"
        assert len(plan.steps) > 0
