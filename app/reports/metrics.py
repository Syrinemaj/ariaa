def compute_rate(value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(value / total, 4)


def compute_success_rate(success_count: int, total_steps: int) -> float:
    return compute_rate(success_count, total_steps)


def compute_error_rate(failed_count: int, total_steps: int) -> float:
    return compute_rate(failed_count, total_steps)
