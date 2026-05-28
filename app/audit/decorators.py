from functools import wraps

from app.audit.service import log_audit_event


def audit_action(action: str, resource_type: str | None = None):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            db = kwargs.get("db")
            current_user = kwargs.get("current_user")

            if db and current_user:
                log_audit_event(
                    db=db,
                    user=current_user,
                    action=action,
                    resource_type=resource_type,
                    metadata={"function": func.__name__},
                )

            return result

        return wrapper

    return decorator
