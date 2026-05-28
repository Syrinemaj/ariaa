from typing import Any, Type, TypeVar

from fastapi import HTTPException
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
