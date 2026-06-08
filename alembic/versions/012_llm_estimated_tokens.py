"""Add estimated_prompt_tokens to llm_calls for pre/post benchmark

Revision ID: 012
Revises: 011
Create Date: 2026-06-08

Changes:
  llm_calls.estimated_prompt_tokens  INTEGER NULL
    — token count measured BEFORE the LLM call via tiktoken / char heuristic.
    NULL for rows created before this migration.

Why:
  Enables the benchmark feature: compare the estimated token count (counted
  from the raw prompt string before submission) against the actual token count
  reported by the API response. A large gap indicates either prompt bloat or
  unexpected context injection that can be optimised.
"""
from alembic import op
import sqlalchemy as sa


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("estimated_prompt_tokens", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "estimated_prompt_tokens")
