"""UserRole values migrate to uppercase + add VIEWER

Revision ID: 008
Revises: 007
Create Date: 2026-05-28

Changes:
1. Drop old CHECK constraint FIRST (allows only lowercase — blocks the UPDATE)
2. UPDATE users SET role = UPPER(role) (safe now, no constraint active)
3. Add new CHECK constraint allowing uppercase + VIEWER
4. Update role column default to 'OPERATOR' (uppercase)

Fix: original migration had steps 1 and 2 in wrong order.
The old ck_users_role constraint (role IN ('admin','operator')) was still
active when the UPDATE tried to write 'ADMIN', causing CheckViolation.
"""
from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop old constraint BEFORE updating values — the old constraint only
    #    allows lowercase ('admin','operator') and would block UPPER() results.
    op.execute("""
        DO $$
        BEGIN
            ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role;
        EXCEPTION WHEN undefined_object THEN NULL;
        END$$;
    """)

    # 2. Migrate existing lowercase roles to uppercase (constraint-free now)
    op.execute(
        "UPDATE users SET role = UPPER(role) WHERE role IN ('admin', 'operator')"
    )

    # 3. Add new CHECK constraint (uppercase values + VIEWER)
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
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role")
    op.execute(
        "UPDATE users SET role = LOWER(role) WHERE role IN ('ADMIN', 'OPERATOR')"
    )
    op.execute("""
        ALTER TABLE users
        ADD CONSTRAINT ck_users_role
        CHECK (role IN ('admin', 'operator'))
    """)
    op.alter_column("users", "role", server_default="operator")
