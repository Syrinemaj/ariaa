"""Tests for Fix 5.2 — task deduplication via Redis lock."""
import time
from unittest.mock import MagicMock, call, patch

import pytest

from app.workers.tasks.deduplication import (
    _sha256,
    batch_key,
    deduplicated_task,
    embedding_key,
    har_pipeline_key,
    report_key,
)


class TestKeyFunctions:
    def test_har_pipeline_key_uses_sha256(self):
        key = har_pipeline_key(file_path="/data/file.har", org_id="org-1")
        assert len(key) == 32  # SHA-256 truncated to 32 hex chars
        assert key == har_pipeline_key(file_path="/data/file.har", org_id="org-1")

    def test_har_pipeline_key_different_orgs(self):
        k1 = har_pipeline_key(file_path="/data/file.har", org_id="org-1")
        k2 = har_pipeline_key(file_path="/data/file.har", org_id="org-2")
        assert k1 != k2

    def test_embedding_key_stable(self):
        assert embedding_key(run_id="run-abc") == "embed:run-abc"

    def test_batch_key_includes_both_parts(self):
        key = batch_key(job_id="job-1", batch_number=3)
        assert "job-1" in key
        assert "3" in key

    def test_report_key_stable(self):
        assert report_key(run_id="run-xyz") == "report:run-xyz"


class TestDeduplicatedTask:
    def _make_redis_mock(self, lock_acquired: bool = True):
        redis = MagicMock()
        redis.set.return_value = lock_acquired  # SET NX returns True if acquired
        return redis

    def test_executes_when_lock_acquired(self):
        redis_mock = self._make_redis_mock(lock_acquired=True)
        executed = []

        with patch("app.workers.tasks.deduplication.get_redis", return_value=redis_mock):
            @deduplicated_task(key_fn=lambda x: f"key:{x}", timeout_seconds=60)
            def my_task(self, x):
                executed.append(x)
                return f"done:{x}"

            self_mock = MagicMock()
            result = my_task(self_mock, "hello")

        assert result == "done:hello"
        assert executed == ["hello"]
        redis_mock.set.assert_called_once()
        redis_mock.delete.assert_called_once()  # lock released

    def test_skips_when_lock_not_acquired(self):
        redis_mock = self._make_redis_mock(lock_acquired=False)
        executed = []

        with patch("app.workers.tasks.deduplication.get_redis", return_value=redis_mock):
            @deduplicated_task(key_fn=lambda x: f"key:{x}", timeout_seconds=60)
            def my_task(self, x):
                executed.append(x)
                return "done"

            result = my_task(MagicMock(), "hello")

        assert result is None   # skipped
        assert executed == []   # not executed

    def test_releases_lock_on_exception(self):
        redis_mock = self._make_redis_mock(lock_acquired=True)

        with patch("app.workers.tasks.deduplication.get_redis", return_value=redis_mock):
            @deduplicated_task(key_fn=lambda: "key", timeout_seconds=60)
            def failing_task(self):
                raise RuntimeError("boom")

            with pytest.raises(RuntimeError, match="boom"):
                failing_task(MagicMock())

        # Lock must be released even on exception
        redis_mock.delete.assert_called_once()

    def test_lock_key_has_correct_prefix(self):
        redis_mock = self._make_redis_mock(lock_acquired=True)
        captured_key = []

        def fake_set(key, value, nx=False, ex=None):
            captured_key.append(key)
            return True

        redis_mock.set.side_effect = fake_set

        with patch("app.workers.tasks.deduplication.get_redis", return_value=redis_mock):
            @deduplicated_task(key_fn=lambda: "my-unique-key", timeout_seconds=60)
            def my_task(self):
                return "ok"

            my_task(MagicMock())

        assert captured_key[0] == "task_lock:my-unique-key"

    def test_lock_ttl_is_respected(self):
        redis_mock = self._make_redis_mock(lock_acquired=True)
        captured_ttl = []

        def fake_set(key, value, nx=False, ex=None):
            captured_ttl.append(ex)
            return True

        redis_mock.set.side_effect = fake_set

        with patch("app.workers.tasks.deduplication.get_redis", return_value=redis_mock):
            @deduplicated_task(key_fn=lambda: "key", timeout_seconds=120)
            def my_task(self):
                return "ok"

            my_task(MagicMock())

        assert captured_ttl[0] == 120
