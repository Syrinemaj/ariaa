"""Add is_team_admin to team_members

Revision ID: 023
Revises: 022
Create Date: 2026-10-08

Every team must have at least one admin: the creator of a team is now
auto-enrolled as its admin member, and the service layer blocks
removing/demoting a team's last remaining admin. Informational only —
does not change route permissions (all team endpoints stay org-admin-gated).
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "team_members",
        sa.Column("is_team_admin", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("team_members", "is_team_admin")
