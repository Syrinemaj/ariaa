def print_ai_usage(tokens_today: int, cost_today: float, high_token_calls: int) -> None:
    print("================ AI USAGE TODAY ================")
    print(f"Tokens today      : {tokens_today:,}")
    print(f"Estimated cost    : ${cost_today:.6f}")
    print(f"High token calls  : {high_token_calls}")
    print("================================================")
