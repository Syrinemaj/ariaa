"""Add governance_policies and forbidden_endpoint_rules

Revision ID: 020
Revises: 019
Create Date: 2026-10-06

Feature: Governance Rules (admin-configurable risk thresholds, forbidden
endpoint patterns, per-environment policy). governance_policies is a
singleton per org (enforced via unique constraint on org_id) — defaults
chosen in app/governance/service.py::get_or_create_policy() reproduce
today's behavior (low risk -> allow, medium/high -> require approval,
every environment unrestricted) so existing orgs see no change until an
admin actually edits the policy. forbidden_endpoint_rules is a list table;
nothing is seeded here — the admin adds rules explicitly (the former
hardcoded "DELETE is always forbidden" in app/security/execution_guard.py
is being replaced by this, not reproduced automatically: see step 9).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "governance_policies",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("risk_threshold_low", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("risk_threshold_high", sa.Integer(), nullable=False, server_default="10"),
        sa.Column(
            "environment_policies",
            JSONB(),
            nullable=False,
            server_default=sa.text(
                "'{\"test\":\"full_access\",\"preprod\":\"full_access\",\"prod\":\"full_access\"}'::jsonb"
            ),
        ),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", name="uq_governance_policies_org_id"),
    )

    op.create_table(
        "forbidden_endpoint_rules",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("method", sa.String(), nullable=True),  # NULL = any method
        sa.Column("path_pattern", sa.String(), nullable=False),  # fnmatch-style, e.g. "/employees/*"
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_forbidden_endpoint_rules_org_id", "forbidden_endpoint_rules", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_forbidden_endpoint_rules_org_id", table_name="forbidden_endpoint_rules")
    op.drop_table("forbidden_endpoint_rules")
    op.drop_table("governance_policies")
