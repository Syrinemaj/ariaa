"""
Tests for the app-agnostic multiplexed-endpoint detector.

Deliberately uses field/value names that do NOT appear anywhere in
canonicalizer.py's fixed SopraHR fallback list (dataSectionName/dsName/
dataStructureName) — the point of this module is to detect the pattern
structurally, for any backend, not just the one it was first observed on.
"""
from app.normalization.action_discriminator import detect_action_discriminator_field


def _invoice_body(op: str) -> dict:
    return {
        "operationType": op,
        "invoiceId": "INV-001",
        "amount": 42.5,
        "currency": "EUR",
    }


def _shipment_body(op: str) -> dict:
    return {
        "operationType": op,
        "trackingCode": "TRK-9",
        "carrier": "dhl",
        "destination": {"country": "FR", "zip": "75001"},
    }


class TestGenericMultiplexedDetection:
    def test_detects_field_that_correlates_with_shape(self):
        bodies = [
            _invoice_body("create_invoice"),
            _invoice_body("create_invoice"),
            _invoice_body("create_invoice"),
            _shipment_body("create_shipment"),
            _shipment_body("create_shipment"),
            _shipment_body("create_shipment"),
        ]
        assert detect_action_discriminator_field(bodies) == "operationType"

    def test_ignores_value_only_variation_same_shape(self):
        # "status" varies but every body has the exact same field set —
        # this is one ordinary operation with different data, not multiplexing.
        bodies = [
            {"status": "pending", "orderId": "1", "total": 10},
            {"status": "shipped", "orderId": "2", "total": 20},
            {"status": "delivered", "orderId": "3", "total": 30},
            {"status": "pending", "orderId": "4", "total": 40},
        ]
        assert detect_action_discriminator_field(bodies) is None

    def test_single_example_returns_none(self):
        # One body, no sibling to compare against — exactly the case
        # dynamic_segment_detector.py and group_normalizer.py also decline
        # to guess on, for the same reason.
        assert detect_action_discriminator_field([_invoice_body("create_invoice")]) is None

    def test_two_examples_one_per_action_is_enough(self):
        # Real captures from a manual test session routinely have just one
        # example per action variant (one leave request, one address
        # change) — the detector must fire on this, not just on large,
        # evenly-balanced synthetic groups.
        bodies = [_invoice_body("create_invoice"), _shipment_body("create_shipment")]
        assert detect_action_discriminator_field(bodies) == "operationType"

    def test_non_dict_bodies_return_none(self):
        assert detect_action_discriminator_field([None, "raw text", 42]) is None

    def test_uniform_shape_across_whole_group_returns_none(self):
        # Every body has identical keys — nothing for any field to explain
        # structurally, no matter how many distinct values operationType
        # takes. One ordinary operation called with different data, not
        # multiplexing.
        bodies = [_invoice_body(f"op_{i}") for i in range(5)]
        assert detect_action_discriminator_field(bodies) is None

    def test_works_for_nested_soprahr_like_shape_without_hardcoded_name(self):
        # Same real-world shape the SopraHR fallback list targets, but with
        # a field name that is NOT in that fixed list — proves detection is
        # structural, not name-based.
        def dossier_body(section: str, extra_fields: dict) -> dict:
            return {"employeeId": "MABR01", "sectionCode": section, "fields": extra_fields}

        bodies = [
            dossier_body("AG", {"startDate": "2026-08-01", "endDate": "2026-08-05", "leaveType": "paid"}),
            dossier_body("AG", {"startDate": "2026-09-01", "endDate": "2026-09-02", "leaveType": "paid"}),
            dossier_body("AG", {"startDate": "2026-10-10", "endDate": "2026-10-11", "leaveType": "unpaid"}),
            dossier_body("AD", {"street": "12 rue Foch", "city": "Nantes", "zip": "44000"}),
            dossier_body("AD", {"street": "3 av Jean", "city": "Lyon", "zip": "69000"}),
            dossier_body("AD", {"street": "8 bd Sud", "city": "Nice", "zip": "06000"}),
        ]
        assert detect_action_discriminator_field(bodies) == "sectionCode"

    def test_deeply_nested_real_world_shape(self):
        # Real body shape captured from a SopraHR HAR: the selector
        # (dataSectionName) sits at depth 4, but the fields that actually
        # make one action structurally different from another — inside
        # dossiers[].sections[].rows[].valueMap — only appear at depth 7.
        # A shallow depth cap sees identical shapes at every level down to
        # the selector and misses the real divergence entirely, returning
        # None on a genuine multiplexed pair.
        def leave_request(motifa=None):
            return {
                "dataStructureName": "ZY",
                "updateMode": " ",
                "dossiers": [{
                    "primaryKey": {"ty": 1, "vl": 34374},
                    "sections": [{
                        "dataSectionName": "AG",
                        "timestamp": "2026-08-11T18:02:01.000Z",
                        "rows": [{"action": 1, "nulign": -100, "valueMap": {
                            "DATDEB": "2026-08-10T00:00:00.000Z",
                            "MOTIFA": motifa,
                            "DATFIN": "2026-08-10T00:00:00.000Z",
                        }}],
                    }],
                }],
            }

        def address_change():
            return {
                "dataStructureName": "ZY",
                "updateMode": " ",
                "dossiers": [{
                    "primaryKey": {"ty": 1, "vl": 34374},
                    "sections": [{
                        "dataSectionName": "AD",
                        "timestamp": "2026-08-11T18:02:01.000Z",
                        "rows": [{"action": 1, "nulign": -100, "valueMap": {
                            "RUE1": "12 rue Foch", "VILLE": "Nantes", "CODPOS": "44000",
                        }}],
                    }],
                }],
            }

        bodies = [leave_request(None), leave_request("ANR"), address_change(), address_change()]
        assert detect_action_discriminator_field(bodies) == "dataSectionName"
