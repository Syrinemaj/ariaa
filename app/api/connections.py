"""Connections endpoints — how ARIA authenticates to a target system at
execution time. Admin-only for every mutation (create/patch/rotate/revoke/
delete/assign-operator). GET and /test are shared with operators, who only
ever see/test connections explicitly assigned to them
(app/connections/service.py::list_usable_connections /
user_can_use_connection) and never the secret.

Secrets are write-only: POST/PATCH accept a `secret` field, nothing this
router returns ever includes encrypted_secret or a decrypted value — see
_connection_response() below, the single place a Connection is serialized.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin, require_admin_or_operator
from app.connections import service as connection_service
from app.db.session import get_db
from app.models.connection import Connection
from app.models.user import User, UserRole

router = APIRouter(prefix="/connections", tags=["Connections"])


def _is_admin(user: User) -> bool:
    role = user.role if isinstance(user.role, str) else user.role.value
    return role == UserRole.ADMIN.value


def _connection_response(c: Connection, operator_ids: list[str] | None = None) -> dict:
    data = {
        "id": c.id,
        "name": c.name,
        "base_url": c.base_url,
        "environment": c.environment,
        "auth_type": c.auth_type,
        "status": c.status,
        "secret_rotated_at": c.secret_rotated_at.isoformat() if c.secret_rotated_at else None,
        "created_by": c.created_by,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    if operator_ids is not None:
        data["operator_ids"] = operator_ids
    return data


class ConnectionCreateRequest(BaseModel):
    name: str
    base_url: str
    environment: str
    auth_type: str
    secret: str


class ConnectionUpdateRequest(BaseModel):
    name: str | None = None
    base_url: str | None = None
    environment: str | None = None
    auth_type: str | None = None


class SecretRotateRequest(BaseModel):
    secret: str


class OperatorAssignRequest(BaseModel):
    user_id: str


@router.get("", response_model=dict)
async def list_connections_route(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    """Admins see every connection in the org. Operators only see the
    active connections an admin explicitly assigned them to (never the
    full org list, per spec)."""
    if _is_admin(current_user):
        connections = await connection_service.list_connections_for_admin(db, current_user.org_id)
    else:
        connections = await connection_service.list_usable_connections(db, current_user.org_id, current_user)

    return {"connections": [_connection_response(c) for c in connections]}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_connection_route(
    payload: ConnectionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        connection = await connection_service.create_connection(
            db,
            org_id=current_user.org_id,
            name=payload.name,
            base_url=payload.base_url,
            environment=payload.environment,
            auth_type=payload.auth_type,
            secret=payload.secret,
            created_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_CREATED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={"name": connection.name, "environment": connection.environment, "auth_type": connection.auth_type},
    )

    return _connection_response(connection, operator_ids=[])


@router.get("/{connection_id}", response_model=dict)
async def get_connection_route(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    connection = await connection_service.get_connection(db, current_user.org_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    operator_ids = await connection_service.list_operator_ids(db, connection_id)
    return _connection_response(connection, operator_ids=operator_ids)


@router.patch("/{connection_id}", response_model=dict)
async def update_connection_route(
    connection_id: str,
    payload: ConnectionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        connection = await connection_service.update_connection(
            db,
            org_id=current_user.org_id,
            connection_id=connection_id,
            name=payload.name,
            base_url=payload.base_url,
            environment=payload.environment,
            auth_type=payload.auth_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_UPDATED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={
            "name": connection.name, "base_url": connection.base_url,
            "environment": connection.environment, "auth_type": connection.auth_type,
        },
    )

    operator_ids = await connection_service.list_operator_ids(db, connection_id)
    return _connection_response(connection, operator_ids=operator_ids)


@router.post("/{connection_id}/rotate-secret", response_model=dict)
async def rotate_secret_route(
    connection_id: str,
    payload: SecretRotateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        connection = await connection_service.rotate_secret(db, current_user.org_id, connection_id, payload.secret)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_SECRET_ROTATED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={},
    )

    return _connection_response(connection)


@router.post("/{connection_id}/revoke", response_model=dict)
async def revoke_connection_route(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    connection = await connection_service.revoke_connection(db, current_user.org_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_REVOKED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={},
    )

    return _connection_response(connection)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection_route(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    connection = await connection_service.get_connection(db, current_user.org_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    target_name = connection.name
    deleted = await connection_service.delete_connection(db, current_user.org_id, connection_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_DELETED,
        resource_type="connection",
        resource_id=connection_id,
        metadata={"name": target_name},
    )


@router.post("/{connection_id}/reactivate", response_model=dict)
async def reactivate_connection_route(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    connection = await connection_service.reactivate_connection(db, current_user.org_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_UPDATED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={"status": "active"},
    )

    return _connection_response(connection)


@router.post("/{connection_id}/test", response_model=dict)
async def test_connection_route(
    connection_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    # Unlike the mutating routes above (create/patch/rotate/revoke/delete/
    # assign), testing a connection doesn't change anything and is exactly
    # what an operator needs before trusting it in a real execution — same
    # authorization rule already used at execution time (user_can_use_connection,
    # app/api/automation.py), not admin-only.
    connection = await connection_service.get_connection(db, current_user.org_id, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connection not found")
    if not await connection_service.user_can_use_connection(db, connection, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to this connection" if connection.status == "active"
            else "This connection has been revoked",
        )

    result = await connection_service.test_connection(connection)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_TESTED,
        resource_type="connection",
        resource_id=connection.id,
        metadata={"success": result["success"], "status_code": result["status_code"]},
    )

    return result


@router.post("/{connection_id}/operators", response_model=dict, status_code=status.HTTP_201_CREATED)
async def assign_operator_route(
    connection_id: str,
    payload: OperatorAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        await connection_service.assign_operator(db, current_user.org_id, connection_id, payload.user_id)
    except ValueError as exc:
        detail = str(exc)
        http_status = status.HTTP_409_CONFLICT if "already assigned" in detail else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=http_status, detail=detail)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_OPERATOR_ASSIGNED,
        resource_type="connection",
        resource_id=connection_id,
        metadata={"user_id": payload.user_id},
    )

    return {"connection_id": connection_id, "user_id": payload.user_id}


@router.delete("/{connection_id}/operators/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unassign_operator_route(
    connection_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    removed = await connection_service.unassign_operator(db, current_user.org_id, connection_id, user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.CONNECTION_OPERATOR_UNASSIGNED,
        resource_type="connection",
        resource_id=connection_id,
        metadata={"user_id": user_id},
    )
