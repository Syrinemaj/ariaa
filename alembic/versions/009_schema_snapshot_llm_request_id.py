"""Add schema_snapshot to workflows + request_id/celery_task_id to llm_calls

Revision ID: 009
Revises: 008
Create Date: 2026-05-29

Changes:
1. workflows.schema_snapshot  JSONB NULL  — schema state at plan creation time
2. llm_calls.request_id       VARCHAR(36) NULL + index — HTTP correlation ID
3. llm_calls.celery_task_id   VARCHAR(36) NULL          — Celery task correlation

Why:
  schema_snapshot enables drift detection: compare the endpoint schemas that
  existed when a plan was built against those present at execution time, and
  block or warn before the plan runs blind into a broken API.

  request_id / celery_task_id allow every Azure OpenAI call to be traced back
  to the HTTP request or Celery task that triggered it, enabling per-request
  cost attribution and distributed tracing.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Schema snapshot column on workflows
    op.add_column(
        "workflows",
        sa.Column("schema_snapshot", JSONB, nullable=True),
    )

    # 2. Request correlation columns on llm_calls
    op.add_column(
        "llm_calls",
        sa.Column("request_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "llm_calls",
        sa.Column("celery_task_id", sa.String(36), nullable=True),
    )

    # Index for fast lookup by request_id (tracing, cost attribution)
    op.create_index(
        "ix_llm_calls_request_id",
        "llm_calls",
        ["request_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_calls_request_id", table_name="llm_calls")
    op.drop_column("llm_calls", "celery_task_id")
    op.drop_column("llm_calls", "request_id")
    op.drop_column("workflows", "schema_snapshot")
