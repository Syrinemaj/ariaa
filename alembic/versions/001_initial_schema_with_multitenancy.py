"""Initial schema baseline (idempotent — safe on existing databases)

Revision ID: 001
Revises:
Create Date: 2026-05-25
"""
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def _existing_tables(bind) -> set:
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    existing = _existing_tables(bind)

    if "organizations" not in existing:
        op.create_table(
            "organizations",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )

    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False),
            sa.Column("email", sa.String(), nullable=False),
            sa.Column("full_name", sa.String(), nullable=True),
            sa.Column("hashed_password", sa.String(), nullable=False),
            sa.Column("role", sa.String(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        op.create_index("ix_users_org_id", "users", ["org_id"])
        op.create_index("ix_users_email", "users", ["email"])

    if "audit_logs" not in existing:
        op.create_table(
            "audit_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), nullable=True),
            sa.Column("action", sa.String(), nullable=False),
            sa.Column("resource_type", sa.String(), nullable=True),
            sa.Column("resource_id", sa.String(), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_audit_logs_org_id", "audit_logs", ["org_id"])

    if "analysis_runs" not in existing:
        op.create_table(
            "analysis_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.String(), nullable=True),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("total_cleaned_api_calls", sa.Integer(), nullable=True),
            sa.Column("total_normalized_endpoints", sa.Integer(), nullable=True),
            sa.Column("total_schema_results", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_analysis_runs_org_id", "analysis_runs", ["org_id"])
        op.create_index("ix_analysis_runs_created_by_user_id", "analysis_runs", ["created_by_user_id"])

    if "endpoints" not in existing:
        op.create_table(
            "endpoints",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False, server_default=""),
            sa.Column("run_id", sa.String(), nullable=False),
            sa.Column("method", sa.String(), nullable=False),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("canonical_key", sa.String(), nullable=False),
            sa.Column("source_count", sa.Integer(), nullable=True),
            sa.Column("business_domain", sa.String(), nullable=True),
            sa.Column("business_action", sa.String(), nullable=True),
            sa.Column("path_parameters", JSONB(), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_endpoints_canonical_key", "endpoints", ["canonical_key"])
        op.create_index("ix_endpoints_org_id", "endpoints", ["org_id"])

    if "endpoint_schemas" not in existing:
        op.create_table(
            "endpoint_schemas",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False, server_default=""),
            sa.Column("endpoint_id", sa.String(), nullable=False),
            sa.Column("request_schema", JSONB(), nullable=True),
            sa.Column("response_schema", JSONB(), nullable=True),
            sa.Column("status_codes", ARRAY(sa.Integer()), nullable=True),
            sa.Column("auth_required", sa.Boolean(), nullable=True),
            sa.Column("auth_type", sa.String(), nullable=True),
            sa.Column("auth_location", sa.String(), nullable=True),
            sa.Column("auth_header_name", sa.String(), nullable=True),
            sa.Column("auth_confidence", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_endpoint_schemas_org_id", "endpoint_schemas", ["org_id"])

    if "workflows" not in existing:
        op.create_table(
            "workflows",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("run_id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("business_domain", sa.String(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "workflow_steps" not in existing:
        op.create_table(
            "workflow_steps",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("workflow_id", sa.String(), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("method", sa.String(), nullable=False),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("canonical_key", sa.String(), nullable=False),
            sa.Column("action", sa.String(), nullable=True),
            sa.Column("depends_on", JSONB(), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "endpoint_embeddings" not in existing:
        op.create_table(
            "endpoint_embeddings",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("endpoint_id", sa.String(), nullable=False),
            sa.Column("embedding_text", sa.String(), nullable=False),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["endpoint_id"], ["endpoints.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("endpoint_id", name="uq_endpoint_embedding_endpoint_id"),
        )
        op.create_index("ix_endpoint_embeddings_endpoint_id", "endpoint_embeddings", ["endpoint_id"])
        op.execute(
            "ALTER TABLE endpoint_embeddings "
            "ADD COLUMN embedding vector(1536) NOT NULL "
            "DEFAULT array_fill(0, ARRAY[1536])::vector"
        )

    if "automation_runs" not in existing:
        op.create_table(
            "automation_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.String(), nullable=True),
            sa.Column("analysis_run_id", sa.String(), nullable=False),
            sa.Column("instruction", sa.String(), nullable=False),
            sa.Column("workflow_name", sa.String(), nullable=False),
            sa.Column("dry_run", sa.Boolean(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("total_steps", sa.Integer(), nullable=True),
            sa.Column("success_count", sa.Integer(), nullable=True),
            sa.Column("failed_count", sa.Integer(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("plan_json", JSONB(), nullable=True),
            sa.Column("result_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_automation_runs_org_id", "automation_runs", ["org_id"])
        op.create_index("ix_automation_runs_created_by_user_id", "automation_runs", ["created_by_user_id"])

    if "automation_step_logs" not in existing:
        op.create_table(
            "automation_step_logs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("automation_run_id", sa.String(), nullable=False),
            sa.Column("step_order", sa.Integer(), nullable=False),
            sa.Column("method", sa.String(), nullable=False),
            sa.Column("path", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=True),
            sa.Column("request_payload", JSONB(), nullable=True),
            sa.Column("response_payload", JSONB(), nullable=True),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["automation_run_id"], ["automation_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "data_files" not in existing:
        op.create_table(
            "data_files",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("org_id", sa.String(), nullable=False, server_default=""),
            sa.Column("created_by_user_id", sa.String(), nullable=True),
            sa.Column("analysis_run_id", sa.String(), nullable=False),
            sa.Column("file_name", sa.String(), nullable=False),
            sa.Column("file_type", sa.String(), nullable=False),
            sa.Column("rows_count", sa.Integer(), nullable=True),
            sa.Column("columns", JSONB(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"]),
            sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_data_files_org_id", "data_files", ["org_id"])
        op.create_index("ix_data_files_created_by_user_id", "data_files", ["created_by_user_id"])

    if "data_rows" not in existing:
        op.create_table(
            "data_rows",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("data_file_id", sa.String(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("raw_data", JSONB(), nullable=True),
            sa.Column("normalized_data", JSONB(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.ForeignKeyConstraint(["data_file_id"], ["data_files.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "field_mappings" not in existing:
        op.create_table(
            "field_mappings",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("analysis_run_id", sa.String(), nullable=False),
            sa.Column("source_field", sa.String(), nullable=False),
            sa.Column("target_field", sa.String(), nullable=False),
            sa.Column("target_endpoint_key", sa.String(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("source", sa.String(), nullable=True),
            sa.Column("approved", sa.Boolean(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "bulk_validation_runs" not in existing:
        op.create_table(
            "bulk_validation_runs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("data_file_id", sa.String(), nullable=False),
            sa.Column("total_rows", sa.Integer(), nullable=True),
            sa.Column("valid_rows", sa.Integer(), nullable=True),
            sa.Column("invalid_rows", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["data_file_id"], ["data_files.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "bulk_validation_errors" not in existing:
        op.create_table(
            "bulk_validation_errors",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("validation_run_id", sa.String(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("field_name", sa.String(), nullable=True),
            sa.Column("error_code", sa.String(), nullable=False),
            sa.Column("message", sa.String(), nullable=False),
            sa.ForeignKeyConstraint(["validation_run_id"], ["bulk_validation_runs.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "automation_approvals" not in existing:
        op.create_table(
            "automation_approvals",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("automation_run_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("approved_by", sa.String(), nullable=True),
            sa.Column("comment", sa.String(), nullable=True),
            sa.Column("approved_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "idempotency_records" not in existing:
        op.create_table(
            "idempotency_records",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("automation_run_id", sa.String(), nullable=False),
            sa.Column("data_row_id", sa.String(), nullable=True),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("endpoint_key", sa.String(), nullable=False),
            sa.Column("idempotency_key", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("response_reference", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_idempotency_records_key", "idempotency_records", ["idempotency_key"], unique=True)

    if "bulk_batches" not in existing:
        op.create_table(
            "bulk_batches",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("automation_run_id", sa.String(), nullable=False),
            sa.Column("batch_number", sa.Integer(), nullable=False),
            sa.Column("start_row", sa.Integer(), nullable=True),
            sa.Column("end_row", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("success_count", sa.Integer(), nullable=True),
            sa.Column("failed_count", sa.Integer(), nullable=True),
            sa.Column("metadata_json", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "bulk_batch_rows" not in existing:
        op.create_table(
            "bulk_batch_rows",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("batch_id", sa.String(), nullable=False),
            sa.Column("data_row_id", sa.String(), nullable=False),
            sa.Column("row_index", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.Column("result_json", JSONB(), nullable=True),
            sa.ForeignKeyConstraint(["batch_id"], ["bulk_batches.id"]),
            sa.PrimaryKeyConstraint("id"),
        )

    if "bulk_execution_reports" not in existing:
        op.create_table(
            "bulk_execution_reports",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("automation_run_id", sa.String(), nullable=False),
            sa.Column("total_requested", sa.Integer(), nullable=True),
            sa.Column("success_count", sa.Integer(), nullable=True),
            sa.Column("failed_count", sa.Integer(), nullable=True),
            sa.Column("partial_success_count", sa.Integer(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("row_errors", JSONB(), nullable=True),
            sa.Column("batch_summary", JSONB(), nullable=True),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if "llm_calls" not in existing:
        op.create_table(
            "llm_calls",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("task_name", sa.String(), nullable=False),
            sa.Column("model", sa.String(), nullable=False),
            sa.Column("prompt_tokens", sa.Integer(), nullable=False),
            sa.Column("completion_tokens", sa.Integer(), nullable=False),
            sa.Column("total_tokens", sa.Integer(), nullable=False),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
            sa.Column("is_high_token", sa.Boolean(), nullable=False),
            sa.Column("called_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )


def downgrade() -> None:
    # Downgrade intentionally left minimal — use with care on existing databases
    pass
