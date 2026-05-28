"""
Run from the project root:
    python -m scripts.print_ai_usage_today
"""
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.llm_observability.service import print_current_ai_usage_today

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        print_current_ai_usage_today(db)
    finally:
        db.close()
