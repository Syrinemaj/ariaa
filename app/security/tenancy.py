from typing import Any, List, Type, TypeVar

from fastapi import HTTPException
from sqlalchemy import or_, true
from sqlalchemy.orm import Query, Session

from app.models.user import User

T = TypeVar("T")


def get_org_filter(model: Type[T], org_id: str) -> Any:
    return model.org_id == org_id  # type: ignore[attr-defined]


def scoped_query(db: Session, model: Type[T], org_id: str) -> Query:
    return db.query(model).filter(get_org_filter(model, org_id))


def assert_same_org(resource_org_id: str, current_user: User) -> None:
    if resource_org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to another organization.")


def team_visibility_clause(model: Type[T], current_user: User, team_ids: List[str]) -> Any:
    """ADMIN sees everything (no restriction). OPERATOR sees resources
    belonging to one of their team(s), plus unassigned/org-wide resources
    (team_id IS NULL). An operator on zero teams only sees unassigned ones.

    Composable with .where() (async select) or .filter() (sync Query) —
    mirrors app.notifications.service._visibility_clause."""
    role_value = current_user.role if isinstance(current_user.role, str) else current_user.role.value
    if role_value == "ADMIN":
        return true()
    if team_ids:
        return or_(model.team_id.in_(team_ids), model.team_id.is_(None))  # type: ignore[attr-defined]
    return model.team_id.is_(None)  # type: ignore[attr-defined]
