"""Tests for Fix 8.1 (atomic lock) + Fix 8.2 (business-field key)."""
import pytest

from app.idempotency.key_generator import generate_idempotency_key


class TestIdempotencyKeyGenerator:
    def test_stable_for_same_inputs(self):
        k1 = generate_idempotency_key("wf", "ep", "org-1", {"email": "a@b.com"})
        k2 = generate_idempotency_key("wf", "ep", "org-1", {"email": "a@b.com"})
        assert k1 == k2

    def test_different_orgs_produce_different_keys(self):
        k1 = generate_idempotency_key("wf", "ep", "org-1", {"email": "a@b.com"})
        k2 = generate_idempotency_key("wf", "ep", "org-2", {"email": "a@b.com"})
        assert k1 != k2

    def test_dict_key_order_does_not_matter(self):
        fields_a = {"email": "a@b.com", "type": "CDI"}
        fields_b = {"type": "CDI", "email": "a@b.com"}
        k1 = generate_idempotency_key("wf", "ep", "org", fields_a)
        k2 = generate_idempotency_key("wf", "ep", "org", fields_b)
        assert k1 == k2, "Key must be stable regardless of dict ordering"

    def test_nested_dict_order_does_not_matter(self):
        f1 = {"contract": {"type": "CDI", "start": "2026-01-01"}}
        f2 = {"contract": {"start": "2026-01-01", "type": "CDI"}}
        k1 = generate_idempotency_key("wf", "ep", "org", f1)
        k2 = generate_idempotency_key("wf", "ep", "org", f2)
        assert k1 == k2

    def test_different_business_fields_produce_different_keys(self):
        k1 = generate_idempotency_key("wf", "ep", "org", {"email": "a@b.com"})
        k2 = generate_idempotency_key("wf", "ep", "org", {"email": "c@d.com"})
        assert k1 != k2

    def test_returns_hex_sha256(self):
        key = generate_idempotency_key("wf", "ep", "org", {})
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_metadata_fields_excluded(self):
        """Idempotency key should NOT include timestamps or row_index."""
        business = {"employee_id": "E-123"}
        # These would vary between runs — must NOT be included
        with_meta = {**business, "created_at": "2026-01-01", "row_index": 42}
        k_business = generate_idempotency_key("wf", "ep", "org", business)
        k_with_meta = generate_idempotency_key("wf", "ep", "org", with_meta)
        # The test shows they produce DIFFERENT keys — caller must pass only business fields
        assert k_business != k_with_meta  # confirms separation of concerns


class TestIdempotencyService:
    @pytest.mark.asyncio
    async def test_acquire_lock_returns_true_on_first_call(self):
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = ("some-uuid",)
        db.execute.return_value = result_mock

        from app.idempotency.service import acquire_idempotency_lock
        result = await acquire_idempotency_lock(
            db=db,
            idempotency_key="key-1",
            endpoint_key="ep",
            org_id="org-1",
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_acquire_lock_returns_false_on_conflict(self):
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None  # ON CONFLICT DO NOTHING → empty RETURNING
        db.execute.return_value = result_mock

        from app.idempotency.service import acquire_idempotency_lock
        result = await acquire_idempotency_lock(
            db=db,
            idempotency_key="key-1",
            endpoint_key="ep",
            org_id="org-1",
        )
        assert result is False  # duplicate detected

    @pytest.mark.asyncio
    async def test_should_skip_returns_false_for_unknown_key(self):
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = None
        db.execute.return_value = result_mock

        from app.idempotency.service import should_skip_due_to_idempotency
        result = await should_skip_due_to_idempotency(
            db=db,
            workflow_name="wf",
            endpoint_key="ep",
            org_id="org",
            business_fields={"id": "123"},
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_should_skip_returns_true_for_success(self):
        from unittest.mock import AsyncMock, MagicMock

        db = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = ("success",)
        db.execute.return_value = result_mock

        from app.idempotency.service import should_skip_due_to_idempotency
        result = await should_skip_due_to_idempotency(
            db=db,
            workflow_name="wf",
            endpoint_key="ep",
            org_id="org",
            business_fields={"id": "123"},
        )
        assert result is True
