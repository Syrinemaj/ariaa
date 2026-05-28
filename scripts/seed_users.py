"""
Crée les utilisateurs par défaut (admin + operator).
Run : python -m scripts.seed_users
"""
from app.auth.service import create_user, get_or_create_default_org, get_user_by_email
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.user import UserRole


def seed_users() -> None:
    init_db()

    with SessionLocal() as db:
        org = get_or_create_default_org(db)

        admin_email = "admin@aria.local"
        operator_email = "operator@aria.local"

        if not get_user_by_email(db, admin_email):
            create_user(
                db=db,
                org_id=org.id,
                email=admin_email,
                password="Admin@123",
                full_name="ARIA Admin",
                role=UserRole.ADMIN,
            )
            print("Created admin user")

        if not get_user_by_email(db, operator_email):
            create_user(
                db=db,
                org_id=org.id,
                email=operator_email,
                password="Operator@123",
                full_name="ARIA Operator",
                role=UserRole.OPERATOR,
            )
            print("Created operator user")

        print("\nSeed completed")
        print("Admin    : admin@aria.local    / Admin@123")
        print("Operator : operator@aria.local / Operator@123")


if __name__ == "__main__":
    seed_users()
