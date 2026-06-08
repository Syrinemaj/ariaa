"""Index composites multi-tenant pour les requêtes les plus fréquentes

Revision ID: 006
Revises: 005
Create Date: 2026-05-28

Pourquoi des index composites ?
  Les requêtes ARIA filtrent toujours sur org_id EN PREMIER (multi-tenant).
  Un index sur (org_id, run_id) permet à PostgreSQL de satisfaire
  la condition org_id via l'index sans lire la table, puis de filtrer
  run_id depuis les pages d'index déjà chargées.

  Sans ces index : chaque requête = full table scan sur 10M+ rows.
  Avec ces index : lecture de quelques pages d'index → ~ 1ms.

NOTE: op.execute("COMMIT") a été supprimé.
  CONCURRENTLY est remplacé par des CREATE INDEX IF NOT EXISTS standards.
  Raison :
  - op.execute("COMMIT") casse la gestion de transaction d'Alembic
    → warning "there is no transaction in progress" sur le COMMIT final
  - llm_calls n'a pas de colonne org_id (la table ne suit pas OrgScopedMixin)
    → l'index idx_llm_calls_org_created a été supprimé
  - IF NOT EXISTS garantit l'idempotence sur une ré-exécution partielle
"""
import sqlalchemy as sa
from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

_INDEXES = [
    # endpoints — requêtes par org + run (registry listing)
    ("idx_endpoints_org_run",
     "CREATE INDEX IF NOT EXISTS idx_endpoints_org_run "
     "ON endpoints(org_id, run_id)"),

    # endpoints — requêtes par org + date (pagination)
    ("idx_endpoints_org_created",
     "CREATE INDEX IF NOT EXISTS idx_endpoints_org_created "
     "ON endpoints(org_id, created_at DESC)"),

    # automation_runs — statut + date (dashboard, reprise)
    ("idx_automation_runs_org_status",
     "CREATE INDEX IF NOT EXISTS idx_automation_runs_org_status "
     "ON automation_runs(org_id, status, created_at DESC)"),

    # llm_calls — coût par tâche + date (reporting LLM)
    # NOTE: llm_calls n'a pas org_id (pas de OrgScopedMixin).
    #       Index sur task_name + called_at pour les agrégations par tâche.
    ("idx_llm_calls_task_created",
     "CREATE INDEX IF NOT EXISTS idx_llm_calls_task_created "
     "ON llm_calls(task_name, called_at DESC)"),

    # bulk_batches — reprise par statut
    ("idx_bulk_batches_run_status",
     "CREATE INDEX IF NOT EXISTS idx_bulk_batches_run_status "
     "ON bulk_batches(automation_run_id, status)"),

    # users — lookup par org + rôle (admin panel)
    ("idx_users_org_role",
     "CREATE INDEX IF NOT EXISTS idx_users_org_role "
     "ON users(org_id, role, is_active)"),

    # audit_logs — pagination par org + date
    ("idx_audit_logs_org_created",
     "CREATE INDEX IF NOT EXISTS idx_audit_logs_org_created "
     "ON audit_logs(org_id, created_at DESC)"),
]

_DROP_INDEXES = [name for name, _ in _INDEXES]


def upgrade() -> None:
    for _, ddl in _INDEXES:
        op.execute(ddl)


def downgrade() -> None:
    for name in reversed(_DROP_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
