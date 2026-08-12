"""Remove VIEWER role

Revision ID: 014
Revises: 013
Create Date: 2026-08-10

VIEWER (Lecteur) was never assigned to a real account and the read-only
permission tier it implied was never enforced anywhere in the app — only
ADMIN and OPERATOR carry real behavior. Reassign any VIEWER row to OPERATOR
before tightening the CHECK constraint (defensive: none exist at the time
of writing, but this must be safe on any environment).
"""
from alembic import op

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("UPDATE users SET role = 'OPERATOR' WHERE role = 'VIEWER'")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('ADMIN', 'OPERATOR'))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER'))
    """)
