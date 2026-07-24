"""
Print what our actual (lifetime) LLM token usage would cost under every
priced model — the current Groq model vs. the Amazon Bedrock Claude
candidates (Haiku 4.5 / Sonnet 5 / Opus 4.8) — cheapest first.

Run from the project root:
    python -m scripts.compare_llm_models
"""
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.llm_observability.service import get_model_cost_comparison

if __name__ == "__main__":
    init_db()
    db = SessionLocal()
    try:
        result = get_model_cost_comparison(db)
    finally:
        db.close()

    based_on = result["based_on"]
    print(
        f"Based on {based_on['total_calls']} calls "
        f"({based_on['total_prompt_tokens']:,} prompt + "
        f"{based_on['total_completion_tokens']:,} completion tokens)\n"
    )
    print(
        f"Current: {result['current_provider']}/{result['current_model']} "
        f"— actual cost so far: ${result['current_actual_cost_usd']:.4f}\n"
    )

    header = f"{'MODEL':<28}{'PROVIDER':<12}{'$/1K IN':>10}{'$/1K OUT':>10}{'PROJECTED $':>14}"
    print(header)
    print("-" * len(header))
    for row in result["projected_by_model"]:
        marker = " <- current" if row["model"] == result["current_model"] else ""
        print(
            f"{row['model']:<28}{row['provider']:<12}"
            f"{row['input_per_1k']:>10.5f}{row['output_per_1k']:>10.5f}"
            f"{row['estimated_cost_usd']:>14.4f}{marker}"
        )

    cheapest = result["projected_by_model"][0]
    current_row = next(
        (r for r in result["projected_by_model"] if r["model"] == result["current_model"]),
        None,
    )
    if current_row is not None and cheapest["model"] != result["current_model"]:
        current_cost = current_row["estimated_cost_usd"]
        if current_cost > 0:
            delta_pct = (current_cost - cheapest["estimated_cost_usd"]) / current_cost * 100
            print(
                f"\n{cheapest['model']} would be {delta_pct:.1f}% cheaper "
                f"than {result['current_model']} at this volume."
            )
