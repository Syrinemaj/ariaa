"""Connections service — async SQLAlchemy (AsyncSession), mirrors
app/teams/service.py and app/governance/service.py.

Secrets never leave this module in plaintext except through
get_decrypted_secret_for_execution(), which exists ONLY for the Celery
worker to call right before the HTTP call to the target system (Phase 1
finding: the pre-Connections auth_headers path put secrets in Celery task
args in plaintext — the fix is that tasks now receive a connection_id and
call that function themselves, inside the worker, never in a task argument).
Every other function here returns a Connection ORM object whose
encrypted_secret field the API route layer (app/api/connections.py) must
never include in a response — see that module's _connection_response().

Audit logging for mutations happens in the API route layer, same split as
governance/teams/users.
"""
from __future__ import annotations

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.connections.crypto import decrypt_secret, encrypt_secret
from app.models.automation import AutomationRun
from app.models.connection import Connection, ConnectionOperator
from app.models.user import User, UserRole
from app.security.ssrf_guard import SSRFError, create_safe_client

VALID_ENVIRONMENTS = {"test", "preprod", "prod"}
VALID_AUTH_TYPES = {"service_account", "oauth_client_credentials", "api_key"}


def _is_admin(user: User) -> bool:
    role = user.role if isinstance(user.role, str) else user.role.value
    return role == UserRole.ADMIN.value


async def create_connection(
    db: AsyncSession,
    org_id: str,
    name: str,
    base_url: str,
    environment: str,
    auth_type: str,
    secret: str,
    created_by: str,
) -> Connection:
    name = name.strip()
    base_url = base_url.strip()
    if not name:
        raise ValueError("name is required")
    if not base_url:
        raise ValueError("base_url is required")
    if environment not in VALID_ENVIRONMENTS:
        raise ValueError(f"environment must be one of {sorted(VALID_ENVIRONMENTS)}")
    if auth_type not in VALID_AUTH_TYPES:
        raise ValueError(f"auth_type must be one of {sorted(VALID_AUTH_TYPES)}")
    if not secret:
        raise ValueError("secret is required")

    connection = Connection(
        org_id=org_id,
        name=name,
        base_url=base_url,
        environment=environment,
        auth_type=auth_type,
        encrypted_secret=encrypt_secret(secret),
        created_by=created_by,
    )
    db.add(connection)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("A connection with this name already exists")

    return connection


async def get_connection(db: AsyncSession, org_id: str, connection_id: str) -> Connection | None:
    result = await db.execute(
        select(Connection).where(Connection.id == connection_id, Connection.org_id == org_id)
    )
    return result.scalar_one_or_none()


async def list_connections_for_admin(db: AsyncSession, org_id: str) -> list[Connection]:
    result = await db.execute(
        select(Connection).where(Connection.org_id == org_id).order_by(Connection.name)
    )
    return list(result.scalars().all())


async def user_can_use_connection(db: AsyncSession, connection: Connection, user: User) -> bool:
    """Single-connection version of list_usable_connections, for the
    execution path (Simple + Bulk Automation) where we already have the
    Connection loaded and just need a yes/no — admins may use any active
    connection in their org, operators only ones they're assigned to."""
    if connection.status != "active":
        return False
    if _is_admin(user):
        return True

    result = await db.execute(
        select(ConnectionOperator).where(
            ConnectionOperator.connection_id == connection.id, ConnectionOperator.user_id == user.id
        )
    )
    return result.scalar_one_or_none() is not None


async def list_usable_connections(db: AsyncSession, org_id: str, user: User) -> list[Connection]:
    """Admins may use any active connection in their org. Operators are
    restricted to connections an admin explicitly assigned them (see
    ConnectionOperator) — this is the enforcement point for the spec's
    'operators see/select only assigned connections, by name'."""
    if _is_admin(user):
        result = await db.execute(
            select(Connection)
            .where(Connection.org_id == org_id, Connection.status == "active")
            .order_by(Connection.name)
        )
        return list(result.scalars().all())

    result = await db.execute(
        select(Connection)
        .join(ConnectionOperator, ConnectionOperator.connection_id == Connection.id)
        .where(
            Connection.org_id == org_id,
            Connection.status == "active",
            ConnectionOperator.user_id == user.id,
        )
        .order_by(Connection.name)
    )
    return list(result.scalars().all())


async def update_connection(
    db: AsyncSession,
    org_id: str,
    connection_id: str,
    name: str | None = None,
    base_url: str | None = None,
    environment: str | None = None,
    auth_type: str | None = None,
) -> Connection | None:
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return None

    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError("name is required")
        connection.name = name
    if base_url is not None:
        base_url = base_url.strip()
        if not base_url:
            raise ValueError("base_url is required")
        connection.base_url = base_url
    if environment is not None:
        if environment not in VALID_ENVIRONMENTS:
            raise ValueError(f"environment must be one of {sorted(VALID_ENVIRONMENTS)}")
        connection.environment = environment
    if auth_type is not None:
        if auth_type not in VALID_AUTH_TYPES:
            raise ValueError(f"auth_type must be one of {sorted(VALID_AUTH_TYPES)}")
        connection.auth_type = auth_type

    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("A connection with this name already exists")

    return connection


async def rotate_secret(db: AsyncSession, org_id: str, connection_id: str, new_secret: str) -> Connection | None:
    from datetime import datetime, timezone

    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return None
    if not new_secret:
        raise ValueError("secret is required")

    connection.encrypted_secret = encrypt_secret(new_secret)
    connection.secret_rotated_at = datetime.now(timezone.utc)
    await db.flush()
    return connection


async def revoke_connection(db: AsyncSession, org_id: str, connection_id: str) -> Connection | None:
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return None

    connection.status = "revoked"
    await db.flush()
    return connection


async def reactivate_connection(db: AsyncSession, org_id: str, connection_id: str) -> Connection | None:
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return None

    connection.status = "active"
    await db.flush()
    return connection


async def delete_connection(db: AsyncSession, org_id: str, connection_id: str) -> bool:
    """Hard delete. ConnectionOperator.connection_id is NOT NULL (no nullable
    path, unlike AutomationRun) so those assignment rows are removed
    outright, same as team_members on user deletion. Historical AutomationRun
    rows are preserved and orphaned (connection_id set NULL), not deleted —
    the execution record and its results stay, just without a live link back
    to a connection that may no longer exist."""
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return False

    await db.execute(delete(ConnectionOperator).where(ConnectionOperator.connection_id == connection_id))
    await db.execute(update(AutomationRun).where(AutomationRun.connection_id == connection_id).values(connection_id=None))
    await db.delete(connection)
    await db.flush()
    return True


async def assign_operator(db: AsyncSession, org_id: str, connection_id: str, user_id: str) -> ConnectionOperator:
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        raise ValueError("Connection not found")

    user_result = await db.execute(select(User).where(User.id == user_id, User.org_id == org_id))
    if user_result.scalar_one_or_none() is None:
        raise ValueError("User not found")

    link = ConnectionOperator(connection_id=connection_id, user_id=user_id)
    db.add(link)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("User is already assigned to this connection")

    return link


async def unassign_operator(db: AsyncSession, org_id: str, connection_id: str, user_id: str) -> bool:
    connection = await get_connection(db, org_id, connection_id)
    if connection is None:
        return False

    result = await db.execute(
        select(ConnectionOperator).where(
            ConnectionOperator.connection_id == connection_id, ConnectionOperator.user_id == user_id
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        return False

    await db.delete(link)
    await db.flush()
    return True


async def list_operator_ids(db: AsyncSession, connection_id: str) -> list[str]:
    result = await db.execute(
        select(ConnectionOperator.user_id).where(ConnectionOperator.connection_id == connection_id)
    )
    return [row[0] for row in result.all()]


def get_decrypted_secret_for_execution(connection: Connection) -> str:
    """Call ONLY from the Celery worker, immediately before the HTTP call to
    the target system. Never call from an API route or anywhere the result
    could end up in a response, a log line, or a task argument."""
    return decrypt_secret(connection.encrypted_secret)


def build_auth_headers(auth_type: str, secret: str) -> dict[str, str]:
    """The equivalent of the old free-text auth_headers dict (see
    app/automation/executor.py, app/workers/tasks/execution.py — both take a
    raw headers dict and pass it straight to httpx), derived from a
    Connection instead. No real OAuth client-credentials token-fetch flow
    (Phase 3 decision) — oauth_client_credentials uses the stored secret
    directly as a bearer token, same as service_account; only the label
    differs, for the admin's own bookkeeping."""
    if auth_type == "api_key":
        return {"X-API-Key": secret}
    if auth_type in ("service_account", "oauth_client_credentials"):
        return {"Authorization": f"Bearer {secret}"}
    return {}


async def test_connection(connection: Connection) -> dict:
    """Simple GET probe against the connection's base_url (Phase 3 decision
    — no endpoint-specific probing). Never raises; always returns a
    response-safe dict (no secret, ever)."""
    secret = decrypt_secret(connection.encrypted_secret)
    headers = build_auth_headers(connection.auth_type, secret)

    try:
        async with create_safe_client(
            base_url=connection.base_url,
            timeout=httpx.Timeout(connect=8.0, read=10.0, write=10.0, pool=5.0),
        ) as client:
            response = await client.get("/", headers=headers)
    except SSRFError as exc:
        return {"success": False, "status_code": None, "message": str(exc)}
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.TimeoutException):
        return {
            "success": False,
            "status_code": None,
            "message": "Cannot reach the target — check the base URL and network.",
        }
    except Exception as exc:
        return {"success": False, "status_code": None, "message": f"Cannot reach the target — {exc}"}

    if response.status_code == 401:
        return {"success": False, "status_code": 401, "message": "Unauthorized — the stored secret was rejected."}
    if response.status_code == 403:
        return {"success": False, "status_code": 403, "message": "Forbidden — the stored secret lacks access."}
    if response.status_code >= 400:
        return {
            "success": False,
            "status_code": response.status_code,
            "message": f"Target returned HTTP {response.status_code}.",
        }

    return {"success": True, "status_code": response.status_code, "message": "Connection reachable."}
