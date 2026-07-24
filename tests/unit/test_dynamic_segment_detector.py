"""Tests for app/normalization/dynamic_segment_detector.py — cross-request
statistical detection of dynamic path segments, for ID formats that don't
match any of the anticipated regex patterns in parameter_detector.py."""
from app.normalization.dynamic_segment_detector import detect_dynamic_positions


class TestDetectDynamicPositions:
    def test_single_varying_position_detected(self):
        paths = [
            ("GET", ["employees", "emp_1"]),
            ("GET", ["employees", "emp_2"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 2)] == {1}

    def test_static_path_stays_static(self):
        paths = [
            ("GET", ["employees", "active"]),
            ("GET", ["employees", "active"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 2)] == set()

    def test_single_observation_cannot_be_dynamic(self):
        # Nothing to compare against — must not guess.
        paths = [("GET", ["employees", "emp_1"])]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 2)] == set()

    def test_two_independent_dynamic_positions_resolved_via_third_sample(self):
        # Neither pair alone isolates both positions — the third sample does.
        paths = [
            ("GET", ["employees", "emp_1", "contracts", "ctr_1"]),
            ("GET", ["employees", "emp_2", "contracts", "ctr_2"]),
            ("GET", ["employees", "emp_1", "contracts", "ctr_3"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 4)] == {1, 3}

    def test_different_methods_kept_separate(self):
        paths = [
            ("GET", ["employees", "emp_1"]),
            ("POST", ["employees", "emp_2"]),
        ]
        result = detect_dynamic_positions(paths)
        # Each method has only one sample of its own shape — no pairing possible.
        assert result[("GET", 2)] == set()
        assert result[("POST", 2)] == set()

    def test_different_lengths_kept_separate(self):
        paths = [
            ("GET", ["employees", "emp_1"]),
            ("GET", ["employees", "emp_1", "contracts"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 2)] == set()
        assert result[("GET", 3)] == set()

    def test_exact_duplicates_do_not_fabricate_signal(self):
        paths = [
            ("GET", ["employees", "emp_1"]),
            ("GET", ["employees", "emp_1"]),
            ("GET", ["employees", "emp_1"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 2)] == set()

    def test_empty_input(self):
        assert detect_dynamic_positions([]) == {}

    def test_does_not_collapse_distinct_resources_after_version_prefix(self):
        # Regression: /api/v1/employees, /api/v1/products, /api/v1/contracts,
        # /api/v1/payments, /api/v1/orders all differ at exactly one position
        # with everything else constant — textbook match for the heuristic,
        # but position 2 enumerates distinct top-level resources, not IDs of
        # one resource. An earlier version of this module fabricated a
        # "/api/v1/{v1_id}" endpoint that merged all five together.
        paths = [
            ("POST", ["api", "v1", "employees"]),
            ("POST", ["api", "v1", "products"]),
            ("POST", ["api", "v1", "contracts"]),
            ("POST", ["api", "v1", "payments"]),
            ("POST", ["api", "v1", "orders"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("POST", 3)] == set()

    def test_still_detects_real_id_even_with_version_prefix_earlier(self):
        # The exclusion only applies to the position directly after a static
        # segment — a real ID further down the path must still be detected.
        paths = [
            ("GET", ["api", "v1", "employees", "emp_1"]),
            ("GET", ["api", "v1", "employees", "emp_2"]),
        ]
        result = detect_dynamic_positions(paths)
        assert result[("GET", 4)] == {3}
