"""
init_db — initialisation de la base au démarrage.

Utilise le sync_engine (psycopg2) car Base.metadata.create_all()
et CREATE EXTENSION ne sont pas disponibles nativement en async.

En production : alembic upgrade head est préféré à create_all.
init_db() garde create_all comme filet de sécurité pour les envs de dev.
"""
from sqlalchemy import text

from app.db.session import sync_engine

# Import ALL models so SQLAlchemy metadata is populated before create_all
from app.models.organization import Organization  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.analysis_run import AnalysisRun  # noqa: F401
from app.models.endpoint import Endpoint  # noqa: F401
from app.models.schema import EndpointSchema  # noqa: F401
from app.models.workflow import WorkflowModel, WorkflowStepModel  # noqa: F401
from app.models.embedding import EndpointEmbedding  # noqa: F401
from app.models.automation import AutomationRun, AutomationStepLog  # noqa: F401
from app.models.data_file import DataFile, DataRow  # noqa: F401
from app.models.field_mapping import FieldMapping  # noqa: F401
from app.models.bulk_validation import BulkValidationRun, BulkValidationError  # noqa: F401
from app.models.approval import AutomationApproval  # noqa: F401
from app.models.idempotency import IdempotencyRecord  # noqa: F401
from app.models.bulk_batch import BulkBatch, BulkBatchRow  # noqa: F401
from app.models.bulk_report import BulkExecutionReport  # noqa: F401
from app.models.llm_call import LLMCall  # noqa: F401
from app.db.base import Base


def init_db() -> None:
    with sync_engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.commit()

    # create_all is safe to call multiple times (IF NOT EXISTS semantics).
    # In production, rely on alembic upgrade head instead.
    Base.metadata.create_all(bind=sync_engine)
