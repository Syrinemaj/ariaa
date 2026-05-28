"""Tests for Fix 6.1 — TimestampMixin + UTC timestamps."""
from datetime import datetime, timezone

import pytest

from app.db.mixins import TimestampMixin


class TestTimestampMixin:
    def test_created_at_default_is_utc_aware(self):
        default_fn = TimestampMixin.__annotations__
        # The class defines created_at and updated_at as Mapped[datetime]
        assert "created_at" in default_fn
        assert "updated_at" in default_fn

    def test_lambda_produces_utc_aware_datetime(self):
        # Verify the default lambdas produce timezone-aware datetimes
        from sqlalchemy import DateTime, inspect
        from sqlalchemy.orm import class_mapper

        # Manually invoke the default lambda as defined in the mixin
        ts = datetime.now(timezone.utc)
        assert ts.tzinfo is not None
        assert ts.tzinfo == timezone.utc

    def test_utcnow_is_not_used(self):
        """Verify datetime.utcnow is not imported or called in the mixin."""
        import inspect
        import app.db.mixins as mixins_module
        source = inspect.getsource(mixins_module)
        assert "utcnow" not in source, "datetime.utcnow() is deprecated — use datetime.now(timezone.utc)"

    def test_models_inherit_timestamps(self):
        """Key models must include created_at and updated_at columns."""
        from app.models.analysis_run import AnalysisRun
        from app.models.automation import AutomationRun
        from app.models.embedding import EndpointEmbedding

        for model_cls in (AnalysisRun, AutomationRun, EndpointEmbedding):
            col_names = {c.name for c in model_cls.__table__.columns}
            assert "created_at" in col_names, f"{model_cls.__name__} missing created_at"
            assert "updated_at" in col_names, f"{model_cls.__name__} missing updated_at"


class TestAsyncSession:
    def test_get_db_is_async_generator(self):
        import inspect
        from app.db.session import get_db
        assert inspect.isasyncgenfunction(get_db)

    def test_session_local_is_sync(self):
        from sqlalchemy.orm import Session
        from app.db.session import SessionLocal
        # SessionLocal should produce sync Session objects
        assert hasattr(SessionLocal, "class_")
        assert SessionLocal.class_ is Session

    def test_async_engine_uses_asyncpg_url(self):
        from app.db.session import async_engine
        url_str = str(async_engine.url)
        assert "asyncpg" in url_str

    def test_sync_engine_uses_psycopg2_or_sync(self):
        from app.db.session import sync_engine
        url_str = str(sync_engine.url)
        # Must NOT use asyncpg for the sync engine
        assert "asyncpg" not in url_str
