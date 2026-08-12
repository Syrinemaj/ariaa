"""
Notification feed — two audiences (see app/models/notification.py):

  create_bulk_launch_notification()       -> team-wide, every ADMIN in org_id
  create_run_completed_notification()     -> the one user who launched the run
  create_approval_required_notification[_async]() -> team-wide, every ADMIN in org_id

Creators come in sync/async pairs because callers run on different session
types: app/api/bulk.py and app/workers/tasks/execution.py use the sync
Session (see app/db/session.py::get_sync_db / SessionLocal), while
app/api/automation.py uses the async Session. The list/count/mark-read
helpers below always run on the async Session used by the polling GET
endpoints in app/api/notifications.py.

Scope: "team-wide" here means org-wide (see app/models/organization.py) — an
admin sees these notifications for their whole org, an operator sees only
notifications addressed to them personally. There is a separate Team model
now (app/models/team.py, used for scoping AnalysisRun/AutomationRun
visibility), but notifications are not scoped by it — this module's "team"
predates that feature and still means "org."
"""
from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.user import User, UserRole


def create_bulk_launch_notification(
    db: Session,
    *,
    operator: User,
    resource_id: str,
    har_file_name: str | None,
    action: str = "BULK_EXECUTION_STARTED",
) -> Notification:
    """Team-wide: every ADMIN sharing operator.org_id sees this."""
    notification = Notification(
        org_id=operator.org_id,
        created_by_user_id=operator.id,
        recipient_user_id=None,
        action=action,
        resource_type="data_file",
        resource_id=resource_id,
        har_file_name=har_file_name,
        is_read=False,
    )
    db.add(notification)
    db.flush()
    return notification


def create_run_completed_notification(
    db: Session,
    *,
    org_id: str,
    launcher_user_id: str,
    resource_id: str,
    har_file_name: str | None,
    action: str,
) -> Notification:
    """Personal: only launcher_user_id (whoever launched the run) sees this."""
    notification = Notification(
        org_id=org_id,
        created_by_user_id=launcher_user_id,
        recipient_user_id=launcher_user_id,
        action=action,
        resource_type="automation_run",
        resource_id=resource_id,
        har_file_name=har_file_name,
        is_read=False,
    )
    db.add(notification)
    db.flush()
    return notification


def _build_approval_required_notification(
    *,
    requester: User,
    resource_type: str,
    resource_id: str | None,
    har_file_name: str | None,
    action: str,
) -> Notification:
    return Notification(
        org_id=requester.org_id,
        created_by_user_id=requester.id,
        recipient_user_id=None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        har_file_name=har_file_name,
        is_read=False,
    )


def create_approval_required_notification(
    db: Session,
    *,
    requester: User,
    resource_type: str,
    resource_id: str | None,
    har_file_name: str | None,
    action: str = "APPROVAL_REQUIRED",
) -> Notification:
    """Team-wide: every ADMIN sharing requester.org_id sees this."""
    notification = _build_approval_required_notification(
        requester=requester,
        resource_type=resource_type,
        resource_id=resource_id,
        har_file_name=har_file_name,
        action=action,
    )
    db.add(notification)
    db.flush()
    return notification


async def create_approval_required_notification_async(
    db: AsyncSession,
    *,
    requester: User,
    resource_type: str,
    resource_id: str | None,
    har_file_name: str | None,
    action: str = "APPROVAL_REQUIRED",
) -> Notification:
    """Async counterpart of create_approval_required_notification (see app/api/automation.py)."""
    notification = _build_approval_required_notification(
        requester=requester,
        resource_type=resource_type,
        resource_id=resource_id,
        har_file_name=har_file_name,
        action=action,
    )
    db.add(notification)
    await db.flush()
    return notification


def _serialize(notification: Notification, operator_name: str | None) -> dict:
    return {
        "id": notification.id,
        "operator_name": operator_name or "Unknown",
        "action": notification.action,
        "har_file_name": notification.har_file_name,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


def _visibility_clause(user: User):
    """ADMIN: team-wide notifications + anything addressed to them personally.
    OPERATOR: only notifications addressed to them personally."""
    if user.role == UserRole.ADMIN:
        return or_(Notification.recipient_user_id.is_(None), Notification.recipient_user_id == user.id)
    return Notification.recipient_user_id == user.id


async def list_notifications(
    db: AsyncSession,
    user: User,
    unread_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    query = (
        select(Notification, User.full_name)
        .outerjoin(User, User.id == Notification.created_by_user_id)
        .where(Notification.org_id == user.org_id, _visibility_clause(user))
    )
    if unread_only:
        query = query.where(Notification.is_read.is_(False))
    query = query.order_by(Notification.created_at.desc()).limit(limit)

    result = await db.execute(query)
    return [_serialize(notification, operator_name) for notification, operator_name in result.all()]


async def count_unread(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.org_id == user.org_id,
            _visibility_clause(user),
            Notification.is_read.is_(False),
        )
    )
    return result.scalar_one()


async def mark_notification_read(db: AsyncSession, user: User, notification_id: str) -> bool:
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.org_id == user.org_id,
            _visibility_clause(user),
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        return False
    notification.is_read = True
    await db.flush()
    return True


async def mark_all_notifications_read(db: AsyncSession, user: User) -> int:
    result = await db.execute(
        select(Notification).where(
            Notification.org_id == user.org_id,
            _visibility_clause(user),
            Notification.is_read.is_(False),
        )
    )
    notifications = result.scalars().all()
    for notification in notifications:
        notification.is_read = True
    await db.flush()
    return len(notifications)
