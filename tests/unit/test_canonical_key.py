"""Tests for Fix 1.2 — org-scoped canonical key."""
import pytest

from app.normalization.canonicalizer import build_canonical_key, build_registry_key


class TestBuildCanonicalKey:
    def test_basic(self):
        assert build_canonical_key("GET", "/users") == "GET /users"

    def test_method_uppercased(self):
        assert build_canonical_key("get", "/users") == "GET /users"

    def test_trailing_slash_stripped(self):
        assert build_canonical_key("POST", "/users/") == "POST /users"

    def test_missing_leading_slash_added(self):
        assert build_canonical_key("DELETE", "users/1") == "DELETE /users/1"

    def test_root_slash_preserved(self):
        assert build_canonical_key("GET", "/") == "GET /"

    def test_discriminator_field_appended_when_present(self):
        key = build_canonical_key(
            "POST", "/rpc/dossier",
            request_body={"sectionCode": "AG", "employeeId": "MABR01"},
            discriminator_field="sectionCode",
        )
        assert key == "POST /rpc/dossier#AG"

    def test_discriminator_field_ignored_when_absent_from_body(self):
        key = build_canonical_key(
            "POST", "/rpc/dossier",
            request_body={"employeeId": "MABR01"},
            discriminator_field="sectionCode",
        )
        assert key == "POST /rpc/dossier"

    def test_falls_back_to_fixed_list_without_discriminator_field(self):
        key = build_canonical_key(
            "POST", "/hr-rich-client/hrservlet/services/openhr/msg-update-dossier",
            request_body={"dataSectionName": "AG"},
        )
        assert key.endswith("#AG")

    def test_explicit_none_does_not_fall_back_to_fixed_list(self):
        # Batch detection ran (action_discriminator.py) and concluded there
        # is no discriminator for this endpoint — that verdict must stick,
        # even though the body happens to also contain a field from the
        # legacy SopraHR-specific list. Otherwise the "generic" pipeline
        # path silently re-depends on the SopraHR-only fallback whenever
        # detection returns nothing, which is exactly what discriminator_field
        # exists to prevent.
        key = build_canonical_key(
            "POST", "/hr-rich-client/hrservlet/services/openhr/msg-update-dossier",
            request_body={"dataSectionName": "AG"},
            discriminator_field=None,
        )
        assert key == "POST /hr-rich-client/hrservlet/services/openhr/msg-update-dossier"


class TestBuildRegistryKey:
    def test_includes_org_id(self):
        key = build_registry_key("org-abc", "GET", "/users")
        assert key.startswith("org-abc:")

    def test_format(self):
        assert build_registry_key("org-1", "POST", "/orders") == "org-1:POST /orders"

    def test_different_orgs_produce_different_keys(self):
        k1 = build_registry_key("org-1", "GET", "/users")
        k2 = build_registry_key("org-2", "GET", "/users")
        assert k1 != k2

    def test_same_org_same_endpoint_equal(self):
        k1 = build_registry_key("org-x", "GET", "/users")
        k2 = build_registry_key("org-x", "get", "/users/")
        assert k1 == k2  # canonicalization normalises method + trailing slash
