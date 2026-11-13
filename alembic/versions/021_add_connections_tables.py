"""Add connections and connection_operators

Revision ID: 021
Revises: 020
Create Date: 2026-10-06

Feature: Connections — how ARIA authenticates to a target system at
execution time, replacing the free-text base_url/auth_headers passed
per-call today (see Phase 1 finding: app/api/automation.py's
ExecutePlanRequest.auth_headers currently flows through Celery task
arguments in plaintext). encrypted_secret is a Fernet token (base64 text,
see app/connections/crypto.py in step 3) — never queried or indexed on,
only ever read back whole and decrypted in the Celery worker.
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connections",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("base_url", sa.String(), nullable=False),
        sa.Column("environment", sa.String(), nullable=False),  # test | preprod | prod
        sa.Column("auth_type", sa.String(), nullable=False),    # service_account | oauth_client_credentials | api_key
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),  # active | revoked
        sa.Column("secret_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "name", name="uq_connections_org_id_name"),
    )
    op.create_index("ix_connections_org_id", "connections", ["org_id"])

    op.create_table(
        "connection_operators",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("connection_id", sa.String(), sa.ForeignKey("connections.id"), nullable=False),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("connection_id", "user_id", name="uq_connection_operators_connection_id_user_id"),
    )
    op.create_index("ix_connection_operators_connection_id", "connection_operators", ["connection_id"])
    op.create_index("ix_connection_operators_user_id", "connection_operators", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_connection_operators_user_id", table_name="connection_operators")
    op.drop_index("ix_connection_operators_connection_id", table_name="connection_operators")
    op.drop_table("connection_operators")

    op.drop_index("ix_connections_org_id", table_name="connections")
    op.drop_table("connections")
