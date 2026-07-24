"""Regression tests for two URL-normalization correctness bugs (ARIA-NORM-FIX).

dynamic_segment_detector.py used to flag ANY path position that varied
across sibling requests as dynamic, purely by pairwise positional diff, with
no check that the differing VALUES actually look like an ID. Two confirmed
symptoms of that single root cause:

  Bug 1 — unrelated sibling resources sharing (method, segment_count) and
  differing at exactly one position (POST /api/v1/hr/employees vs
  .../departments) collapsed into one fake templated endpoint
  (POST /api/v1/hr/{hr_id}).

  Bug 2 — same mechanism, one position further: once the true ID position
  was excluded from future pairwise diff-counts (the detector's fixed-point
  loop), an adjacent literal action segment (contract vs salary) could
  become "the sole remaining difference" and get wrongly flagged too — then
  named from the RAW previous segment (the ID's own concrete value):
  .../emp_301/contract -> {emp_301_id}.

Fix: a position is only ever marked dynamic if BOTH differing values
independently look ID-shaped (parameter_detector.detect_parameter_type) —
plain resource-name words never do, no matter how much they vary
positionally. A second, independent guard in infer_parameter_name()'s
previous-segment fallback refuses to derive a name from a previous segment
that is itself ID-shaped, as defense in depth.

All tests here run with use_ai=False (no live/mocked LLM calls needed) —
every case is resolvable by rules + the fixed detector alone.
"""
from __future__ import annotations

import re
from typing import List, Set

from app.ingestion.models import TrafficEntry
from app.normalization.dynamic_segment_detector import detect_dynamic_positions
from app.normalization.parameter_detector import infer_parameter_name
from app.normalization.service import normalize_entries


def _entries(method: str, paths: List[str]) -> List[TrafficEntry]:
    return [TrafficEntry(method=method, url=f"https://example.com{p}", path=p) for p in paths]


def _templates(method: str, paths: List[str]) -> Set[str]:
    endpoints = normalize_entries(_entries(method, paths), use_ai=False, deduplicate=True)
    return {ep.normalized_path for ep in endpoints}


class TestSingleResourceIdCollapsesToOneTemplate:
    def test_employees_multiple_ids_collapse_to_one_template(self):
        templates = _templates("GET", [
            "/hr/employees/emp_101",
            "/hr/employees/emp_102",
            "/hr/employees/emp_205",
        ])
        assert templates == {"/hr/employees/{employee_id}"}

    def test_nested_action_emp_id_plus_contract_stays_one_template(self):
        templates = _templates("POST", [
            f"/hr/employees/emp_{n}/contract" for n in (301, 302, 303, 304, 305, 306)
        ])
        assert templates == {"/hr/employees/{employee_id}/contract"}

    def test_two_level_dynamic_department_and_employee(self):
        templates = _templates("GET", [
            "/hr/departments/dept_10/employees/emp_101",
            "/hr/departments/dept_10/employees/emp_102",
            "/hr/departments/dept_20/employees/emp_201",
            "/hr/departments/dept_20/employees/emp_202",
            "/hr/departments/dept_30/employees/emp_301",
        ])
        assert templates == {"/hr/departments/{department_id}/employees/{employee_id}"}

    def test_cart_items_cart_id_dynamic_items_stays_literal(self):
        templates = _templates("GET", [
            "/shop/carts/cart_7001/items",
            "/shop/carts/cart_7002/items",
            "/shop/carts/cart_7104/items",
        ])
        assert templates == {"/shop/carts/{cart_id}/items"}


class TestBug1SiblingResourcesStayLiteral:
    """POST /api/v1/hr/employees vs POST /api/v1/hr/departments must NOT
    collapse into POST /api/v1/hr/{hr_id} — they're two distinct resources,
    not two values of the same parameter."""

    def test_employees_and_departments_do_not_collapse(self):
        templates = _templates("POST", [
            "/api/v1/hr/employees",
            "/api/v1/hr/departments",
        ])
        assert templates == {"/api/v1/hr/employees", "/api/v1/hr/departments"}
        assert "/api/v1/hr/{hr_id}" not in templates

    def test_employees_alone_stays_literal(self):
        templates = _templates("POST", ["/hr/employees"])
        assert templates == {"/hr/employees"}

    def test_login_stays_literal(self):
        templates = _templates("POST", ["/auth/login"])
        assert templates == {"/auth/login"}

    def test_login_and_logout_siblings_do_not_collapse(self):
        templates = _templates("POST", ["/auth/login", "/auth/logout"])
        assert templates == {"/auth/login", "/auth/logout"}
        assert not any("{" in t for t in templates)


class TestBug2NoRawIdLeaksIntoParameterName:
    """Reproduces the exact reported cascade: once emp_NNN (a real, varying
    ID) is correctly detected dynamic, a sibling action segment (contract vs
    salary) must not become "the sole remaining difference" and get named
    from the raw ID value of the previous segment."""

    def test_contract_and_salary_siblings_do_not_leak_raw_id_into_name(self):
        templates = _templates("POST", [
            "/hr/employees/emp_301/contract",
            "/hr/employees/emp_302/contract",
            "/hr/employees/emp_303/salary",
            "/hr/employees/emp_304/salary",
        ])
        assert templates == {
            "/hr/employees/{employee_id}/contract",
            "/hr/employees/{employee_id}/salary",
        }
        # The exact reported symptom: no parameter name may embed a raw ID.
        assert not any(re.search(r"\{[a-z]+_\d+_id\}", t) for t in templates)


class TestSingleObservationStillDetectedByShape:
    """Point 7 of the spec: an ID seen only ONCE at a position must still be
    templated via shape (regex) — unlike dynamic_segment_detector.py's
    cross-request comparison, which needs >=2 samples to infer anything
    from pure positional variance, shape-based detection works from a
    single example. Documented behavior, not a gap."""

    def test_single_prefixed_id_still_templated(self):
        templates = _templates("GET", ["/hr/employees/emp_999"])
        assert templates == {"/hr/employees/{employee_id}"}

    def test_single_unknown_prefix_id_still_templated_low_confidence(self):
        # "wgt" has no entry in _PREFIX_TO_PARAM -> low-confidence generic
        # name, but the segment is still templated (not left literal) —
        # low confidence only gates whether the LLM gets a chance to
        # refine it (skipped here, use_ai=False), not whether it templates.
        templates = _templates("GET", ["/api/widgets/wgt_042"])
        assert templates == {"/api/widgets/{resource_id}"}


class TestDetectDynamicPositionsShapeGate:
    """Unit-level coverage directly on the detector, independent of the
    full normalize_entries() pipeline."""

    def test_plain_word_variance_never_marked_dynamic(self):
        result = detect_dynamic_positions([
            ("POST", ["api", "v1", "hr", "employees"]),
            ("POST", ["api", "v1", "hr", "departments"]),
        ])
        assert result[("POST", 4)] == set()

    def test_id_shaped_variance_still_marked_dynamic(self):
        result = detect_dynamic_positions([
            ("GET", ["hr", "employees", "emp_101"]),
            ("GET", ["hr", "employees", "emp_102"]),
        ])
        assert result[("GET", 3)] == {2}

    def test_cascade_does_not_flag_adjacent_literal_action(self):
        # Reproduces Bug 2's exact mechanism at the detector level: once
        # position 2 (the real ID) is marked dynamic and excluded from
        # future diff-counts, position 3 (contract/salary) must NOT become
        # "the sole remaining difference".
        result = detect_dynamic_positions([
            ("POST", ["hr", "employees", "emp_301", "contract"]),
            ("POST", ["hr", "employees", "emp_302", "contract"]),
            ("POST", ["hr", "employees", "emp_303", "salary"]),
        ])
        assert result[("POST", 4)] == {2}  # only the real ID position


class TestInferParameterNameGuardsAgainstIdShapedPreviousSegment:
    """Fix B — second line of defense: previous_segment must not itself
    look ID-shaped, or its raw value would leak into the derived name."""

    def test_previous_segment_id_shaped_falls_back_to_generic(self):
        name, source, confidence = infer_parameter_name(
            previous_segment="emp_301",
            detected_type="observed_variable",
            raw_value="contract",
        )
        assert name == "id"
        assert "emp_301" not in name

    def test_previous_segment_real_resource_name_still_works(self):
        name, source, confidence = infer_parameter_name(
            previous_segment="employees",
            detected_type="observed_variable",
            raw_value="emp_301",
        )
        assert name == "employee_id"
