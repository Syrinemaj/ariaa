from typing import Any, Type, TypeVar

from fastapi import HTTPException
from sqlalchemy import or_, select, true
from sqlalchemy.orm import Query, Session

from app.models.team_member import TeamMember
from app.models.user import User

T = TypeVar("T")


def get_org_filter(model: Type[T], org_id: str) -> Any:
    return model.org_id == org_id  # type: ignore[attr-defined]


def scoped_query(db: Session, model: Type[T], org_id: str) -> Query:
    return db.query(model).filter(get_org_filter(model, org_id))


def assert_same_org(resource_org_id: str, current_user: User) -> None:
    if resource_org_id != current_user.org_id:
        raise HTTPException(status_code=403, detail="Access denied: resource belongs to another organization.")


def owner_visibility_clause(model: Type[T], current_user: User) -> Any:
    """ADMIN sees every resource in the org (no restriction). OPERATOR sees
    resources they created themselves, OR resources tagged (team_id) to any
    team they belong to — "members of a team see the same activity, analyzed
    by anyone in the team." A resource with team_id=NULL (its creator wasn't
    in exactly one team when it was made — see
    app/teams/service.py::resolve_single_team_id) stays visible only to its
    creator and admins; that's a separate, narrower gap, not reopened here.

    The team check is a correlated subquery (team_ids the user belongs to),
    not a prior single-resolved-team_id match — so it still works for a user
    in 2+ teams. No extra DB round-trip: it's inlined into the same query.

    Composable with .where() (async select) or .filter() (sync Query)."""
    role_value = current_user.role if isinstance(current_user.role, str) else current_user.role.value
    if role_value == "ADMIN":
        return true()
    my_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == current_user.id).scalar_subquery()
    return or_(
        model.created_by_user_id == current_user.id,  # type: ignore[attr-defined]
        model.team_id.in_(my_team_ids),  # type: ignore[attr-defined]
    )
