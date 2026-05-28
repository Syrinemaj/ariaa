"""Add org_id and created_by_user_id to existing tables

Revision ID: 002
Revises: 001
Create Date: 2026-05-25
"""
import sqlalchemy as sa

from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def _existing_columns(bind, table: str) -> set:
    return {col["name"] for col in sa.inspect(bind).get_columns(table)}


def _existing_indexes(bind, table: str) -> set:
    return {idx["name"] for idx in sa.inspect(bind).get_indexes(table)}


def _add_index_if_missing(bind, index_name: str, table: str, columns: list) -> None:
    if index_name not in _existing_indexes(bind, table):
        cols = ", ".join(columns)
        op.execute(f"CREATE INDEX {index_name} ON {table} ({cols})")


def upgrade() -> None:
    bind = op.get_bind()

    # analysis_runs
    cols = _existing_columns(bind, "analysis_runs")
    if "org_id" not in cols:
        op.execute("ALTER TABLE analysis_runs ADD COLUMN org_id VARCHAR NOT NULL DEFAULT ''")
        _add_index_if_missing(bind, "ix_analysis_runs_org_id", "analysis_runs", ["org_id"])
    if "created_by_user_id" not in cols:
        op.execute("ALTER TABLE analysis_runs ADD COLUMN created_by_user_id VARCHAR")
        _add_index_if_missing(bind, "ix_analysis_runs_created_by_user_id", "analysis_runs", ["created_by_user_id"])

    # endpoints
    cols = _existing_columns(bind, "endpoints")
    if "org_id" not in cols:
        op.execute("ALTER TABLE endpoints ADD COLUMN org_id VARCHAR NOT NULL DEFAULT ''")
        _add_index_if_missing(bind, "ix_endpoints_org_id", "endpoints", ["org_id"])

    # endpoint_schemas
    cols = _existing_columns(bind, "endpoint_schemas")
    if "org_id" not in cols:
        op.execute("ALTER TABLE endpoint_schemas ADD COLUMN org_id VARCHAR NOT NULL DEFAULT ''")
        _add_index_if_missing(bind, "ix_endpoint_schemas_org_id", "endpoint_schemas", ["org_id"])

    # automation_runs
    cols = _existing_columns(bind, "automation_runs")
    if "org_id" not in cols:
        op.execute("ALTER TABLE automation_runs ADD COLUMN org_id VARCHAR NOT NULL DEFAULT ''")
        _add_index_if_missing(bind, "ix_automation_runs_org_id", "automation_runs", ["org_id"])
    if "created_by_user_id" not in cols:
        op.execute("ALTER TABLE automation_runs ADD COLUMN created_by_user_id VARCHAR")
        _add_index_if_missing(bind, "ix_automation_runs_created_by_user_id", "automation_runs", ["created_by_user_id"])

    # data_files
    cols = _existing_columns(bind, "data_files")
    if "org_id" not in cols:
        op.execute("ALTER TABLE data_files ADD COLUMN org_id VARCHAR NOT NULL DEFAULT ''")
        _add_index_if_missing(bind, "ix_data_files_org_id", "data_files", ["org_id"])
    if "created_by_user_id" not in cols:
        op.execute("ALTER TABLE data_files ADD COLUMN created_by_user_id VARCHAR")
        _add_index_if_missing(bind, "ix_data_files_created_by_user_id", "data_files", ["created_by_user_id"])


def downgrade() -> None:
    op.execute("ALTER TABLE data_files DROP COLUMN IF EXISTS created_by_user_id")
    op.execute("ALTER TABLE data_files DROP COLUMN IF EXISTS org_id")
    op.execute("ALTER TABLE automation_runs DROP COLUMN IF EXISTS created_by_user_id")
    op.execute("ALTER TABLE automation_runs DROP COLUMN IF EXISTS org_id")
    op.execute("ALTER TABLE endpoint_schemas DROP COLUMN IF EXISTS org_id")
    op.execute("ALTER TABLE endpoints DROP COLUMN IF EXISTS org_id")
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS created_by_user_id")
    op.execute("ALTER TABLE analysis_runs DROP COLUMN IF EXISTS org_id")
