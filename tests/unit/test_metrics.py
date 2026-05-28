import pytest
from app.reports.metrics import compute_rate, compute_success_rate, compute_error_rate


class TestComputeRate:
    def test_normal(self):
        assert compute_rate(3, 10) == 0.3

    def test_zero_total_returns_zero(self):
        assert compute_rate(5, 0) == 0.0

    def test_full_success(self):
        assert compute_rate(10, 10) == 1.0

    def test_zero_value(self):
        assert compute_rate(0, 10) == 0.0

    def test_rounds_to_4_decimals(self):
        assert compute_rate(1, 3) == 0.3333


class TestSuccessRate:
    def test_normal(self):
        assert compute_success_rate(7, 10) == 0.7

    def test_all_failed(self):
        assert compute_success_rate(0, 10) == 0.0

    def test_empty(self):
        assert compute_success_rate(0, 0) == 0.0


class TestErrorRate:
    def test_normal(self):
        assert compute_error_rate(2, 10) == 0.2

    def test_all_failed(self):
        assert compute_error_rate(10, 10) == 1.0

    def test_empty(self):
        assert compute_error_rate(0, 0) == 0.0
