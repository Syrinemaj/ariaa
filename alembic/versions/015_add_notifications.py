"""Add notifications table

Revision ID: 015
Revises: 014
Create Date: 2026-08-10

Backs the admin notification feed: each admin sees a live feed of the bulk
automation runs launched by the operators in their org ("team"), including
the HAR file name behind the run.
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("org_id", sa.String(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("resource_type", sa.String(), nullable=True),
        sa.Column("resource_id", sa.String(), nullable=True),
        sa.Column("har_file_name", sa.String(), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_org_id", "notifications", ["org_id"])
    op.create_index("ix_notifications_created_by_user_id", "notifications", ["created_by_user_id"])
    op.create_index(
        "ix_notifications_org_unread",
        "notifications",
        ["org_id", "is_read"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_org_unread", table_name="notifications")
    op.drop_index("ix_notifications_created_by_user_id", table_name="notifications")
    op.drop_index("ix_notifications_org_id", table_name="notifications")
    op.drop_table("notifications")
