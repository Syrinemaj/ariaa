"""Tests for Fix 1.1 — workflow clustering."""
import pytest

from app.normalization.models import NormalizedEndpoint
from app.workflows.clustering import _cluster_endpoints, _path_prefix, discover_workflows


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
        assert _path_prefix("/users/123/orders") == "/users/orders"

    def test_parameterized_path(self):
        # {id} segments are skipped
        assert _path_prefix("/users/{id}/orders") == "/users/orders"

    def test_root_path(self):
        assert _path_prefix("/") == "/"

    def test_single_segment(self):
        assert _path_prefix("/users") == "/users"


class TestClusterEndpoints:
    def test_groups_by_domain(self):
        endpoints = [
            _make_ep("/invoices", domain="finance"),
            _make_ep("/payments", domain="finance"),
            _make_ep("/employees", domain="hr"),
            _make_ep("/contracts", domain="hr"),
        ]
        clusters = _cluster_endpoints(endpoints)
        assert len(clusters) == 2
        domains = {
            frozenset(ep.metadata.get("business_domain") for ep in cluster)
            for cluster in clusters
        }
        assert {"finance"} in domains
        assert {"hr"} in domains

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
        # Should still return exactly one cluster (the catch-all)
        assert len(clusters) == 1
        assert clusters[0][0].normalized_path == "/only-one"

    def test_mixed_domain_and_no_domain(self):
        endpoints = [
            _make_ep("/invoices", domain="finance"),
            _make_ep("/payments", domain="finance"),
            _make_ep("/orders/1"),  # no domain
            _make_ep("/orders/2"),  # no domain
        ]
        clusters = _cluster_endpoints(endpoints)
        assert len(clusters) == 2


class TestDiscoverWorkflows:
    def test_returns_one_workflow_per_cluster(self):
        endpoints = [
            _make_ep("/invoices", domain="finance"),
            _make_ep("/payments", domain="finance"),
            _make_ep("/employees", domain="hr"),
            _make_ep("/contracts", domain="hr"),
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
