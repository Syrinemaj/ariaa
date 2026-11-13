"""Only availability problems may open the circuit breaker, not per-row data errors."""
import pytest

from app.bulk_execution.batch_executor import is_health_failure


@pytest.mark.parametrize("status_code", [500, 502, 503, 504, 408, 429])
def test_server_errors_timeouts_and_throttling_count(status_code):
    assert is_health_failure(status_code) is True


def test_network_error_without_response_counts():
    # e.g. connection refused while the target is down
    assert is_health_failure(None, "All connection attempts failed") is True


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 409, 422])
def test_client_data_errors_do_not_count(status_code):
    # Observed in a real run: five 422 rows opened the breaker for the whole file.
    assert is_health_failure(status_code) is False


@pytest.mark.parametrize("message", [
    "Security: path traversal in parameter",
    "Validation error: 'email' is a required property",
])
def test_errors_raised_before_sending_do_not_count(message):
    assert is_health_failure(None, message) is False
