"""User security hardening: brute-force protection, refresh tokens, TIMESTAMPTZ

Revision ID: 003
Revises: 002
Create Date: 2026-05-28
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def _col_exists(bind, table: str, column: str) -> bool:
    cols = {c["name"] for c in sa.inspect(bind).get_columns(table)}
    return column in cols


def _table_exists(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def upgrade() -> None:
    bind = op.get_bind()

    # ── users ────────────────────────────────────────────────────────────────

    # Convert naive timestamp columns to TIMESTAMPTZ
    for col in ("created_at",):
        op.execute(
            f"ALTER TABLE users ALTER COLUMN {col} "
            f"TYPE TIMESTAMPTZ USING {col} AT TIME ZONE 'UTC'"
        )

    # Brute-force / lockout fields
    if not _col_exists(bind, "users", "failed_login_count"):
        op.add_column(
            "users",
            sa.Column(
                "failed_login_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )

    if not _col_exists(bind, "users", "locked_until"):
        op.add_column(
            "users",
            sa.Column(
                "locked_until",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if not _col_exists(bind, "users", "last_login_at"):
        op.add_column(
            "users",
            sa.Column(
                "last_login_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if not _col_exists(bind, "users", "password_changed_at"):
        op.add_column(
            "users",
            sa.Column(
                "password_changed_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    if not _col_exists(bind, "users", "updated_at"):
        op.add_column(
            "users",
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=True,
            ),
        )

    # Enforce valid role values at DB level
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'ck_users_role'
            ) THEN
                ALTER TABLE users
                ADD CONSTRAINT ck_users_role
                CHECK (role IN ('admin', 'operator'));
            END IF;
        END$$;
    """)

    # Case-insensitive unique index on email
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email_lower
        ON users (lower(email));
    """)

    # ── organizations ────────────────────────────────────────────────────────

    op.execute(
        "ALTER TABLE organizations ALTER COLUMN created_at "
        "TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"
    )

    # ── audit_logs ───────────────────────────────────────────────────────────

    op.execute(
        "ALTER TABLE audit_logs ALTER COLUMN created_at "
        "TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'"
    )

    # ── refresh_tokens ───────────────────────────────────────────────────────

    if not _table_exists(bind, "refresh_tokens"):
        op.create_table(
            "refresh_tokens",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column(
                "user_id",
                sa.String(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ip_address", sa.String(45), nullable=True),
            sa.Column("user_agent", sa.String(512), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_refresh_tokens_user_id",
            "refresh_tokens",
            ["user_id"],
        )
        op.create_index(
            "ix_refresh_tokens_expires_at",
            "refresh_tokens",
            ["expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _table_exists(bind, "refresh_tokens"):
        op.drop_table("refresh_tokens")

    op.execute("DROP INDEX IF EXISTS ix_users_email_lower")

    op.execute("""
        ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role;
    """)

    for col in ("updated_at", "password_changed_at", "last_login_at", "locked_until", "failed_login_count"):
        if _col_exists(bind, "users", col):
            op.drop_column("users", col)
