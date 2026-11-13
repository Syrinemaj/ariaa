"""Tests for Fix 1.1 — workflow clustering."""
import pytest

from app.normalization.models import NormalizedEndpoint
from app.workflows.clustering import (
    _CATCHALL_DOMAIN,
    _build_llm_groups,
    _cluster_endpoints,
    _path_prefix,
    discover_workflows,
)


def _make_ep(path: str, method: str = "GET", domain: str | None = None) -> NormalizedEndpoint:
    return NormalizedEndpoint(
        method=method,
        original_url=f"https://api.example.com{path}",
        original_path=path,
        normalized_path=path,
        canonical_key=f"{method} {path}",
        metadata={"business_domain": domain} if domain else {},
    )


class TestPathPrefix:
    def test_simple_path(self):
        # _path_prefix only ever runs on already-normalized paths (the
        # pipeline templates raw IDs into {param} before clustering) — a
        # plain literal path with no parameters keeps its first `depth`
        # segments as-is.
        assert _path_prefix("/users/orders/history") == "/users/orders"

    def test_parameterized_path(self):
        # {id} segments are skipped
        assert _path_prefix("/users/{id}/orders") == "/users/orders"

    def test_root_path(self):
        assert _path_prefix("/") == "/"

    def test_single_segment(self):
        assert _path_prefix("/users") == "/users"


class TestClusterEndpoints:
    def test_groups_by_functional_category(self):
        # Grouping key is the path-keyword taxonomy (_FUNCTIONAL_CATEGORIES),
        # not business_domain — that field is free-text LLM output and the
        # same real HAR yields a dozen near-synonyms for one obvious category
        # ("human_resources" / "Human Resources" / "hr_operations" / ...).
        endpoints = [
            _make_ep("/hr-rich-client/hrservlet/services/openhr/msg-get-dossier-data", method="POST"),
            _make_ep("/hr-rich-client/hrservlet/services/openhr/msg-update-dossier", method="POST"),
            _make_ep("/cxf/messageservice/l10n/messages/page.login/fr_fr"),
            _make_ep("/cxf/messageservice/l10n/messages/page.expertiframe/fr_fr"),
        ]
        clusters = _cluster_endpoints(endpoints)
        assert len(clusters) == 2
        categories = set()
        for cluster, _is_catchall, _preset in clusters:
            paths = {ep.normalized_path for ep in cluster}
            if any("hrservlet" in p for p in paths):
                categories.add("hr_employee_dossier")
            if any("l10n/messages" in p for p in paths):
                categories.add("localization")
        assert categories == {"hr_employee_dossier", "localization"}

    def test_groups_ungrouped_by_prefix(self):
        endpoints = [
            _make_ep("/orders/1"),
            _make_ep("/orders/2"),
            _make_ep("/products/a"),
            _make_ep("/products/b"),
        ]
        clusters = _cluster_endpoints(endpoints)
        assert len(clusters) == 2

    def test_empty_input(self):
        assert _cluster_endpoints([]) == []

    def test_single_endpoint_goes_to_catchall(self):
        # A single endpoint is below MIN_CLUSTER_SIZE → catch-all group
        clusters = _cluster_endpoints([_make_ep("/only-one", domain="finance")])
        # Should still return exactly one cluster (the catch-all), flagged as such
        assert len(clusters) == 1
        cluster, is_catchall, _preset = clusters[0]
        assert cluster[0].normalized_path == "/only-one"
        assert is_catchall is True

    def test_mixed_domain_and_no_domain(self):
        endpoints = [
            _make_ep("/invoices", domain="finance"),
            _make_ep("/payments", domain="finance"),
            _make_ep("/orders/1"),  # no domain
            _make_ep("/orders/2"),  # no domain
        ]
        clusters = _cluster_endpoints(endpoints)
        assert len(clusters) == 2


class TestBuildLlmGroups:
    """
    endpoint_grouping LLM responses are imperfect in practice — observed on
    a real 26-endpoint HAR (historically with Groq's llama-3.3-70b, since
    removed as a provider) that the model drops or duplicates an index
    sometimes. These lock in the salvage behavior: a small gap doesn't
    discard everything, a large one still does.
    """

    def _endpoints(self, n: int) -> list[NormalizedEndpoint]:
        return [_make_ep(f"/item/{i}") for i in range(n)]

    def test_full_coverage_returns_all_groups_no_catchall(self):
        ungrouped = self._endpoints(4)
        groups_data = [
            {"name": "a", "endpoint_indices": [0, 1]},
            {"name": "b", "endpoint_indices": [2, 3]},
        ]
        result = _build_llm_groups(groups_data, ungrouped)
        assert len(result) == 2
        assert all(preset != _CATCHALL_DOMAIN for _members, preset in result)

    def test_one_missing_index_salvaged_into_catchall_not_discarded(self):
        # 3 of 4 endpoints correctly grouped, index 3 never mentioned —
        # must NOT raise/discard the two good groups over this.
        ungrouped = self._endpoints(4)
        groups_data = [
            {"name": "a", "endpoint_indices": [0, 1]},
            {"name": "b", "endpoint_indices": [2]},
        ]
        result = _build_llm_groups(groups_data, ungrouped)
        named_groups = [(m, p) for m, p in result if p != _CATCHALL_DOMAIN]
        catchall_groups = [(m, p) for m, p in result if p == _CATCHALL_DOMAIN]
        assert len(named_groups) == 2
        assert len(catchall_groups) == 1
        assert catchall_groups[0][0] == [ungrouped[3]]

    def test_bad_and_duplicate_indices_skipped_not_raised(self):
        ungrouped = self._endpoints(3)
        groups_data = [
            {"name": "a", "endpoint_indices": [0, 0, 99, "x"]},  # dup, out of range, wrong type
            {"name": "b", "endpoint_indices": [1, 2]},
        ]
        result = _build_llm_groups(groups_data, ungrouped)
        # group "a" ends up with just endpoint 0 (the rest were invalid/dup),
        # group "b" fully valid — nothing raised, nothing salvaged to catch-all.
        by_name = {p["name"]: m for m, p in result if isinstance(p, dict)}
        assert by_name["a"] == [ungrouped[0]]
        assert by_name["b"] == [ungrouped[1], ungrouped[2]]

    def test_majority_missing_raises_instead_of_salvaging(self):
        # Only 1 of 5 endpoints covered — this is the LLM call having
        # failed outright, not "one dropped index". Must still raise so
        # the caller's path-prefix/TF-IDF fallback cascade kicks in,
        # rather than returning one catch-all covering almost everything.
        ungrouped = self._endpoints(5)
        groups_data = [{"name": "a", "endpoint_indices": [0]}]
        with pytest.raises(ValueError):
            _build_llm_groups(groups_data, ungrouped)

    def test_empty_groups_data_raises(self):
        ungrouped = self._endpoints(4)
        with pytest.raises(ValueError):
            _build_llm_groups([], ungrouped)


class TestDiscoverWorkflows:
    def test_returns_one_workflow_per_cluster(self):
        endpoints = [
            _make_ep("/hr-rich-client/hrservlet/services/openhr/msg-get-dossier-data", method="POST"),
            _make_ep("/hr-rich-client/hrservlet/services/openhr/msg-update-dossier", method="POST"),
            _make_ep("/cxf/messageservice/l10n/messages/page.login/fr_fr"),
            _make_ep("/cxf/messageservice/l10n/messages/page.expertiframe/fr_fr"),
        ]
        workflows = discover_workflows(endpoints)
        assert len(workflows) == 2
        for wf in workflows:
            assert len(wf.steps) > 0

    def test_empty_returns_empty(self):
        assert discover_workflows([]) == []

    def test_all_same_domain_returns_one_workflow(self):
        endpoints = [_make_ep(f"/invoices/{i}", domain="finance") for i in range(5)]
        workflows = discover_workflows(endpoints)
        assert len(workflows) == 1
