from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.events import AuditEvent
from app.audit.service import log_audit_event
from app.auth.dependencies import require_admin
from app.db.session import get_db
from app.models.user import User
from app.teams.service import (
    add_member,
    create_team,
    delete_team,
    get_team_with_members,
    list_teams,
    remove_member,
    rename_team,
)

router = APIRouter(prefix="/teams", tags=["Teams"])


class TeamCreateRequest(BaseModel):
    name: str


class TeamRenameRequest(BaseModel):
    name: str


class TeamMemberRequest(BaseModel):
    user_id: str


@router.get("", response_model=dict)
async def list_teams_route(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return {"teams": await list_teams(db, org_id=current_user.org_id)}


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_team_route(
    payload: TeamCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        team = await create_team(db, org_id=current_user.org_id, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.TEAM_CREATED,
        resource_type="team",
        resource_id=team.id,
        metadata={"name": team.name},
    )

    return {"id": team.id, "org_id": team.org_id, "name": team.name, "member_count": 0, "member_user_ids": []}


@router.get("/{team_id}", response_model=dict)
async def get_team_route(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    team = await get_team_with_members(db, team_id=team_id, org_id=current_user.org_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


@router.patch("/{team_id}", response_model=dict)
async def rename_team_route(
    team_id: str,
    payload: TeamRenameRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        team = await rename_team(db, team_id=team_id, org_id=current_user.org_id, name=payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))

    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.TEAM_RENAMED,
        resource_type="team",
        resource_id=team.id,
        metadata={"name": team.name},
    )

    return {"id": team.id, "org_id": team.org_id, "name": team.name}


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team_route(
    team_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    deleted = await delete_team(db, team_id=team_id, org_id=current_user.org_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.TEAM_DELETED,
        resource_type="team",
        resource_id=team_id,
        metadata={},
    )


@router.post("/{team_id}/members", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_team_member_route(
    team_id: str,
    payload: TeamMemberRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    try:
        await add_member(db, team_id=team_id, org_id=current_user.org_id, user_id=payload.user_id)
    except ValueError as exc:
        detail = str(exc)
        http_status = status.HTTP_409_CONFLICT if "already a member" in detail else status.HTTP_404_NOT_FOUND
        raise HTTPException(status_code=http_status, detail=detail)

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.TEAM_MEMBER_ADDED,
        resource_type="team",
        resource_id=team_id,
        metadata={"user_id": payload.user_id},
    )

    return {"team_id": team_id, "user_id": payload.user_id}


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member_route(
    team_id: str,
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    removed = await remove_member(db, team_id=team_id, org_id=current_user.org_id, user_id=user_id)
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")

    await log_audit_event(
        db=db,
        user=current_user,
        action=AuditEvent.TEAM_MEMBER_REMOVED,
        resource_type="team",
        resource_id=team_id,
        metadata={"user_id": user_id},
    )
