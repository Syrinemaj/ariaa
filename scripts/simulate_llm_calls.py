"""
Injecte des appels LLM fictifs pour tester l'affichage terminal.
Run: python -m scripts.simulate_llm_calls
"""
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.llm_observability.repository import create_llm_call
from app.llm_observability.service import print_current_ai_usage_today

FAKE_CALLS = [
    {"task_name": "classify_api_call",  "prompt_tokens": 850,  "completion_tokens": 120},
    {"task_name": "generate_workflow",  "prompt_tokens": 2400, "completion_tokens": 680},
    {"task_name": "classify_api_call",  "prompt_tokens": 760,  "completion_tokens": 95},
    {"task_name": "execute_step",       "prompt_tokens": 3100, "completion_tokens": 420},
    {"task_name": "map_fields",         "prompt_tokens": 510,  "completion_tokens": 75},
]

PROMPT_COST_PER_1K  = 0.00015
COMPLETION_COST_PER_1K = 0.00060
HIGH_TOKEN_THRESHOLD = 3000

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        for call in FAKE_CALLS:
            total = call["prompt_tokens"] + call["completion_tokens"]
            cost  = (call["prompt_tokens"] / 1000 * PROMPT_COST_PER_1K
                   + call["completion_tokens"] / 1000 * COMPLETION_COST_PER_1K)
            high  = total >= HIGH_TOKEN_THRESHOLD
            create_llm_call(
                db=db,
                task_name=call["task_name"],
                model="gpt-4o-mini",
                prompt_tokens=call["prompt_tokens"],
                completion_tokens=call["completion_tokens"],
                total_tokens=total,
                estimated_cost_usd=round(cost, 6),
                is_high_token=high,
            )
            print(f"  [OK] {call['task_name']} — {total} tokens {'(HIGH)' if high else ''}")

        print()
        print_current_ai_usage_today(db)
    finally:
        db.close()
