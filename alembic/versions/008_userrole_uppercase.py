"""UserRole values migrate to uppercase + add VIEWER

Revision ID: 008
Revises: 007
Create Date: 2026-05-28

Changes:
1. UPDATE users SET role = UPPER(role) WHERE role IN ('admin','operator')
2. Drop old CHECK constraint (ck_users_role allows lowercase)
3. Add new CHECK constraint allowing uppercase + VIEWER
4. Update role column default to 'OPERATOR' (uppercase)
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Migrate existing role values to uppercase
    op.execute("UPDATE users SET role = UPPER(role) WHERE role IN ('admin', 'operator')")

    # 2. Drop old CHECK constraint if it exists
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role;
        EXCEPTION WHEN undefined_object THEN NULL;
        END$$;
    """)

    # 3. Add new CHECK constraint (uppercase + VIEWER)
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('ADMIN', 'OPERATOR', 'VIEWER'))
    """)

    # 4. Update column server_default
    op.alter_column(
        "users",
        "role",
        server_default="OPERATOR",
        existing_type=sa.String(),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role
    """)
    op.execute("UPDATE users SET role = LOWER(role) WHERE role IN ('ADMIN', 'OPERATOR')")
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'operator'))
    """)
    op.alter_column("users", "role", server_default="operator")
