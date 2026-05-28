from app.core.config import settings


def estimate_llm_cost(prompt_tokens: int, completion_tokens: int) -> float:
    prompt_cost = (prompt_tokens / 1000) * settings.LLM_PROMPT_COST_PER_1K
    completion_cost = (completion_tokens / 1000) * settings.LLM_COMPLETION_COST_PER_1K
    return round(prompt_cost + completion_cost, 6)


def is_high_token_call(total_tokens: int) -> bool:
    return total_tokens >= settings.LLM_HIGH_TOKEN_THRESHOLD
