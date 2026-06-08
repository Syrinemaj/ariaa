"""
Crée les utilisateurs par défaut (admin + operator).
Run : python -m scripts.seed_users
"""
import asyncio

from app.auth.service import create_user, get_or_create_default_org, get_user_by_email
from app.db.init_db import init_db
from app.db.session import AsyncSessionLocal
from app.models.user import UserRole

ADMIN_EMAIL = "admin@aria-app.dev"
ADMIN_PASSWORD = "Admin@123456!"

OPERATOR_EMAIL = "operator@aria-app.dev"
OPERATOR_PASSWORD = "Operator@123456!"


async def seed_users() -> None:
    init_db()

    async with AsyncSessionLocal() as db:
        org = await get_or_create_default_org(db)

        if not await get_user_by_email(db, ADMIN_EMAIL):
            await create_user(
                db=db,
                org_id=org.id,
                email=ADMIN_EMAIL,
                password=ADMIN_PASSWORD,
                full_name="ARIA Admin",
                role=UserRole.ADMIN,
            )
            print("Created admin user")
        else:
            print("Admin user already exists")

        if not await get_user_by_email(db, OPERATOR_EMAIL):
            await create_user(
                db=db,
                org_id=org.id,
                email=OPERATOR_EMAIL,
                password=OPERATOR_PASSWORD,
                full_name="ARIA Operator",
                role=UserRole.OPERATOR,
            )
            print("Created operator user")
        else:
            print("Operator user already exists")

        await db.commit()

    print("\nSeed completed")
    print(f"Admin    : {ADMIN_EMAIL}    / {ADMIN_PASSWORD}")
    print(f"Operator : {OPERATOR_EMAIL} / {OPERATOR_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(seed_users())
