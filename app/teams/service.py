"""
Teams service — async SQLAlchemy (AsyncSession), mirrors app/auth/service.py.

Phase 1 only: team creation and membership management. Nothing here scopes
any other resource (analysis runs, automation runs, ...) by team — that is
deliberately out of scope until a follow-up phase.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.team import Team
from app.models.team_member import TeamMember
from app.models.user import User


def _team_dict(t: Team, member_count: int = 0, member_user_ids: list[str] | None = None) -> dict:
    return {
        "id": t.id,
        "org_id": t.org_id,
        "name": t.name,
        "member_count": member_count,
        "member_user_ids": member_user_ids or [],
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _member_dict(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "email": u.email,
        "role": u.role,
    }


async def create_team(db: AsyncSession, org_id: str, name: str) -> Team:
    name = name.strip()
    if not name:
        raise ValueError("Team name is required")

    team = Team(org_id=org_id, name=name)
    db.add(team)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("A team with this name already exists")

    return team


async def list_teams(db: AsyncSession, org_id: str) -> list[dict]:
    teams_result = await db.execute(
        select(Team).where(Team.org_id == org_id).order_by(Team.created_at.desc())
    )
    teams = teams_result.scalars().all()
    team_ids = [t.id for t in teams]

    members_by_team: dict[str, list[str]] = {tid: [] for tid in team_ids}
    if team_ids:
        m_result = await db.execute(
            select(TeamMember.team_id, TeamMember.user_id).where(TeamMember.team_id.in_(team_ids))
        )
        for team_id, user_id in m_result.all():
            members_by_team[team_id].append(user_id)

    return [_team_dict(t, len(members_by_team[t.id]), members_by_team[t.id]) for t in teams]


async def get_team_with_members(db: AsyncSession, team_id: str, org_id: str) -> dict | None:
    result = await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))
    team = result.scalar_one_or_none()
    if team is None:
        return None

    members_result = await db.execute(
        select(User)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
        .order_by(User.full_name)
    )
    members = [_member_dict(u) for u in members_result.scalars().all()]
    member_ids = [m["id"] for m in members]

    return {**_team_dict(team, len(members), member_ids), "members": members}


async def rename_team(db: AsyncSession, team_id: str, org_id: str, name: str) -> Team | None:
    name = name.strip()
    if not name:
        raise ValueError("Team name is required")

    result = await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))
    team = result.scalar_one_or_none()
    if team is None:
        return None

    team.name = name
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("A team with this name already exists")

    return team


async def delete_team(db: AsyncSession, team_id: str, org_id: str) -> bool:
    result = await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))
    team = result.scalar_one_or_none()
    if team is None:
        return False

    await db.delete(team)
    await db.flush()
    return True


async def add_member(db: AsyncSession, team_id: str, org_id: str, user_id: str) -> TeamMember:
    team_result = await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))
    if team_result.scalar_one_or_none() is None:
        raise ValueError("Team not found")

    user_result = await db.execute(select(User).where(User.id == user_id, User.org_id == org_id))
    if user_result.scalar_one_or_none() is None:
        raise ValueError("User not found")

    membership = TeamMember(team_id=team_id, user_id=user_id)
    db.add(membership)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ValueError("User is already a member of this team")

    return membership


async def resolve_single_team_id(db: AsyncSession, user_id: str) -> str | None:
    """The user's team_id if they belong to exactly one team, else None
    (0 or 2+ teams — the created resource stays org-wide / unassigned)."""
    result = await db.execute(select(TeamMember.team_id).where(TeamMember.user_id == user_id))
    team_ids = {row[0] for row in result.all()}
    return next(iter(team_ids)) if len(team_ids) == 1 else None


def resolve_single_team_id_sync(db: Session, user_id: str) -> str | None:
    rows = db.query(TeamMember.team_id).filter(TeamMember.user_id == user_id).all()
    team_ids = {row[0] for row in rows}
    return next(iter(team_ids)) if len(team_ids) == 1 else None


async def remove_member(db: AsyncSession, team_id: str, org_id: str, user_id: str) -> bool:
    team_result = await db.execute(select(Team).where(Team.id == team_id, Team.org_id == org_id))
    if team_result.scalar_one_or_none() is None:
        return False

    result = await db.execute(
        select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return False

    await db.delete(membership)
    await db.flush()
    return True
