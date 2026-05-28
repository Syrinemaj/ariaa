def estimate_api_calls(valid_rows: int, steps_count: int) -> int:
    return valid_rows * steps_count


def estimate_duration_seconds(api_calls: int, delay_per_call: float = 0.1) -> float:
    return round(api_calls * delay_per_call, 2)
