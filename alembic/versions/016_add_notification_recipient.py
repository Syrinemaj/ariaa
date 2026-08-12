"""Add notifications.recipient_user_id

Revision ID: 016
Revises: 015
Create Date: 2026-08-10

Notifications now serve two audiences: NULL recipient_user_id means
team-wide (every ADMIN in org_id — an operator launched a bulk run), while
a specific recipient_user_id targets one user (their own bulk run finished).
"""
from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("recipient_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])


def downgrade() -> None:
    op.drop_index("ix_notifications_recipient_user_id", table_name="notifications")
    op.drop_column("notifications", "recipient_user_id")
