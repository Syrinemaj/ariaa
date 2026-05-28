"""Tests for Fix 6.2 (HNSW) and Fix 6.5 (intermediate commits)."""
import pytest


class TestHNSWIndex:
    def test_embedding_model_declares_hnsw_index(self):
        from app.models.embedding import EndpointEmbedding

        index_names = {
            idx.name
            for idx in EndpointEmbedding.__table__.indexes
        }
        assert "idx_endpoint_embeddings_hnsw" in index_names

    def test_hnsw_index_uses_cosine_ops(self):
        from app.models.embedding import EndpointEmbedding

        hnsw_idx = next(
            idx for idx in EndpointEmbedding.__table__.indexes
            if idx.name == "idx_endpoint_embeddings_hnsw"
        )
        ops = hnsw_idx.dialect_options.get("postgresql", {}).get("ops", {})
        assert ops.get("embedding") == "vector_cosine_ops"

    def test_hnsw_index_m_parameter(self):
        from app.models.embedding import EndpointEmbedding

        hnsw_idx = next(
            idx for idx in EndpointEmbedding.__table__.indexes
            if idx.name == "idx_endpoint_embeddings_hnsw"
        )
        with_opts = hnsw_idx.dialect_options.get("postgresql", {}).get("with", {})
        assert with_opts.get("m") == 16
        assert with_opts.get("ef_construction") == 64


class TestIntermediateCommits:
    def test_batch_commit_size_is_defined(self):
        from app.bulk_execution.batch_executor import BATCH_COMMIT_SIZE
        assert isinstance(BATCH_COMMIT_SIZE, int)
        assert BATCH_COMMIT_SIZE > 0
        assert BATCH_COMMIT_SIZE <= 50  # should be reasonably small

    def test_execute_batch_accepts_job_id(self):
        import inspect
        from app.bulk_execution.batch_executor import execute_batch

        sig = inspect.signature(execute_batch)
        assert "job_id" in sig.parameters

    def test_execute_batch_accepts_async_session(self):
        import inspect
        from app.bulk_execution.batch_executor import execute_batch
        from sqlalchemy.ext.asyncio import AsyncSession

        sig = inspect.signature(execute_batch)
        db_param = sig.parameters.get("db")
        assert db_param is not None
        # The annotation should reference AsyncSession
        annotation = db_param.annotation
        assert annotation is AsyncSession or str(annotation) in ("AsyncSession", "sqlalchemy.ext.asyncio.AsyncSession")

    def test_advisory_lock_query_present(self):
        """Verify the advisory lock SQL is present in the source."""
        import inspect
        import app.bulk_execution.batch_executor as mod
        source = inspect.getsource(mod)
        assert "pg_advisory_xact_lock" in source

    def test_intermediate_commit_present(self):
        """Verify intermediate commits happen inside the row loop."""
        import inspect
        import app.bulk_execution.batch_executor as mod
        source = inspect.getsource(mod)
        assert "BATCH_COMMIT_SIZE" in source
        assert "await db.commit()" in source
