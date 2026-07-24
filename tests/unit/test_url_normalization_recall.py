"""
Recall harness for exhaustive URL-ID detection (rules + grouped Groq LLM).

Hits the REAL Groq API (no mocking) — the whole point is to measure actual
detection recall for the PFE evaluation chapter, not a canned mock answer.
Skipped automatically when no GROQ_API_KEY is configured. Not meant to gate
every commit given the external dependency + per-call cost + LLM
non-determinism — run manually:

    pytest tests/unit/test_url_normalization_recall.py -s -v

Each case is a GROUP of sibling URLs sharing one endpoint (method + path
shape) — exactly how normalize_entries() batches requests for the grouped
LLM call (see group_normalizer.py). The full real pipeline runs end to end:
rules -> group_normalizer (LLM only for genuinely ambiguous positions) ->
url_normalizer.normalize_path().

Grading is structural, not string-exact: a segment is scored correct if it
becomes a `{placeholder}` where an ID was expected, or stays literal where a
fixed segment was expected — the exact parameter NAME chosen (e.g. "shop_id"
vs "product_id") is a naming-quality concern, not a detection-recall one,
so it isn't graded here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import FrozenSet, List

import pytest

from app.core.config import settings
from app.ingestion.models import TrafficEntry
from app.normalization import group_normalizer
from app.normalization.service import normalize_entries

pytestmark = pytest.mark.skipif(
    not settings.GROQ_API_KEY,
    reason="requires a real GROQ_API_KEY — not mocked, hits the live Groq API",
)

_PLACEHOLDER_RE = re.compile(r"^\{.+\}$")


def _segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


@dataclass
class RecallCase:
    name: str
    method: str
    urls: List[str]
    id_positions: FrozenSet[int]       # 0-indexed positions expected to become {placeholder}
    fixed_positions: FrozenSet[int]    # 0-indexed positions expected to stay literal
    note: str = ""                     # informational only, printed in the report


# Cases marked "no ground truth" are graded separately (see TestSingleExample).
CASES: List[RecallCase] = [
    RecallCase(
        "entier_simple", "GET",
        ["/api/orders/123", "/api/orders/456", "/api/orders/789"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="entier pur — attendu: rules seules (NUMERIC_ID_PATTERN)",
    ),
    RecallCase(
        "uuid_standard", "GET",
        [
            "/api/sessions/550e8400-e29b-41d4-a716-446655440000",
            "/api/sessions/6ba7b810-9dad-11d1-80b4-00c04fd430c8",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="UUID avec tirets — attendu: rules seules (UUID_PATTERN)",
    ),
    RecallCase(
        "uuid_sans_tirets", "GET",
        [
            "/api/sessions/550e8400e29b41d4a716446655440000",
            "/api/sessions/6ba7b8109dad11d180b400c04fd430c8",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="UUID sans tirets — ne matche pas UUID_PATTERN, attendu: capté via HASH_PATTERN (32 hex)",
    ),
    RecallCase(
        "hash_hex_md5_like", "GET",
        [
            "/api/files/9e107d9d372bb6826bd81d3542a419d6",
            "/api/files/e4d909c290d0fb1ca068ffaddf22cbd0",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="hash 32 hex (MD5-like) — attendu: rules seules (HASH_PATTERN)",
    ),
    RecallCase(
        "hash_hex_sha_like", "GET",
        [
            "/api/commits/2fd4e1c67a2d28fced849ee1bb76e7391b93eb12",
            "/api/commits/a94a8fe5ccb19ba61c4c0873d391e987982fbbd3",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="hash 40 hex (SHA1-like) — attendu: rules seules (HASH_PATTERN)",
    ),
    RecallCase(
        "jwt_like", "GET",
        [
            "/api/tokens/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
            "/api/tokens/eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhYmMifQ.4Q1234abcXyzExampleSignatureHere",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="JWT-like (3 segments base64url) — attendu: rules seules (JWT_PATTERN)",
    ),
    RecallCase(
        "mongo_objectid", "GET",
        [
            "/api/documents/507f1f77bcf86cd799439011",
            "/api/documents/507f191e810c19729de860ea",
        ],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="ObjectId Mongo (24 hex) — attendu: rules seules (HASH_PATTERN)",
    ),
    RecallCase(
        "code_metier_invoice", "GET",
        ["/api/invoices/INV-2024-0891", "/api/invoices/INV-2024-1123", "/api/invoices/INV-2024-7765"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="code métier avec préfixe connu — attendu: rules seules (INVOICE_ID_PATTERN)",
    ),
    RecallCase(
        "code_metier_order_underscore", "GET",
        ["/api/orders/ORD_88213", "/api/orders/ORD_90441", "/api/orders/ORD_10029"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="ORD_xxxxx (underscore, pas tiret) — ne matche AUCUNE regex; "
             "attendu: capté via détection de variabilité inter-requêtes + contexte ('orders')",
    ),
    RecallCase(
        "code_metier_prefixe_inconnu", "GET",
        ["/api/widgets/wgt_alpha_009", "/api/widgets/wgt_beta_014", "/api/widgets/wgt_gamma_027"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="préfixe métier totalement inconnu du dictionnaire de règles — "
             "attendu: rules seules restent ambiguës (confidence 0.45), le LLM DE GROUPE doit trancher",
    ),
    RecallCase(
        "slug_mixte_hyphen", "GET",
        ["/shop/product-8821", "/shop/product-9034", "/shop/product-7756"],
        id_positions=frozenset({1}), fixed_positions=frozenset({0}),
        note="slug texte+id (tiret) — le pipeline actuel templatise le SEGMENT ENTIER "
             "(pas d'isolation de la sous-partie variable), donc {*} attendu sur tout 'product-8821'",
    ),
    RecallCase(
        "slug_mixte_underscore", "GET",
        ["/api/user_45892", "/api/user_78213", "/api/user_11020"],
        id_positions=frozenset({1}), fixed_positions=frozenset({0}),
        note="slug texte+id (underscore) — ne matche aucune regex, "
             "attendu: capté via détection de variabilité inter-requêtes",
    ),
    RecallCase(
        "mot_metier_qui_varie_annee", "GET",
        ["/api/reports/2021", "/api/reports/2022", "/api/reports/2023"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1}),
        note="ressemble à une année mais varie — attendu: détecté comme ID malgré la forme 'légitime'",
    ),
    RecallCase(
        # ARIA-NORM-FIX: was id_positions={2} — dynamic_segment_detector.py
        # used to flag ANY position that varied across sibling requests,
        # shape notwithstanding, which is also the exact mechanism behind
        # two confirmed correctness bugs: unrelated sibling resources
        # (POST /api/v1/hr/employees vs .../departments) collapsed into one
        # fake templated endpoint, and — once the true ID position was
        # excluded from the pairwise diff count — an adjacent literal
        # segment absorbing a raw ID value into its own parameter name
        # (.../emp_301/contract -> {emp_301_id}). Fixed by requiring BOTH
        # differing values to independently look ID-shaped (regex) before a
        # position is ever flagged dynamic. That is a deliberate, disclosed
        # trade-off: a purely alphabetic word that varies (like a status
        # enum used as a path segment) is no longer auto-detected, even
        # though nothing else at that position gives it away. Accepted
        # because a status-as-path-segment is itself an unusual REST
        # convention (a query param `?status=pending` is more common) and
        # the trade-off closes two live catalog-correctness bugs. Status-
        # like segments now need either an explicit rule/prefix entry or
        # enough sibling volume to reach the group LLM via some other
        # already-dynamic position in the same shape.
        "mot_metier_qui_varie_statut", "GET",
        ["/api/workflows/pending", "/api/workflows/active", "/api/workflows/archived"],
        id_positions=frozenset(), fixed_positions=frozenset({0, 1, 2}),
        note="mot alphabétique pur qui varie (statut) — désormais laissé littéral "
             "(compromis accepté, voir commentaire ci-dessus)",
    ),
    RecallCase(
        "segment_fixe_a_ne_pas_templatiser", "GET",
        ["/api/orders/123/details", "/api/orders/456/details", "/api/orders/789/details"],
        id_positions=frozenset({2}), fixed_positions=frozenset({0, 1, 3}),
        note="vérifie qu'on ne sur-détecte PAS 'details' comme variable",
    ),
]


def _run_case(case: RecallCase) -> List[str]:
    entries = [
        TrafficEntry(method=case.method, url=f"https://example.com{u}", path=u)
        for u in case.urls
    ]
    endpoints = normalize_entries(entries, use_ai=True, deduplicate=False)
    return [ep.normalized_path for ep in endpoints]


@dataclass
class Tally:
    id_hits: int = 0
    id_total: int = 0
    fixed_hits: int = 0
    fixed_total: int = 0
    case_results: list = field(default_factory=list)


_TALLY = Tally()


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_recall_case(case: RecallCase):
    normalized_paths = _run_case(case)

    case_id_hits = case_id_total = case_fixed_hits = case_fixed_total = 0
    for path in normalized_paths:
        segs = _segments(path)
        for pos in case.id_positions:
            case_id_total += 1
            if pos < len(segs) and _PLACEHOLDER_RE.match(segs[pos]):
                case_id_hits += 1
        for pos in case.fixed_positions:
            case_fixed_total += 1
            if pos < len(segs) and not _PLACEHOLDER_RE.match(segs[pos]):
                case_fixed_hits += 1

    _TALLY.id_hits += case_id_hits
    _TALLY.id_total += case_id_total
    _TALLY.fixed_hits += case_fixed_hits
    _TALLY.fixed_total += case_fixed_total

    passed = case_id_hits == case_id_total and case_fixed_hits == case_fixed_total
    _TALLY.case_results.append({
        "name": case.name,
        "passed": passed,
        "id_hits": case_id_hits, "id_total": case_id_total,
        "fixed_hits": case_fixed_hits, "fixed_total": case_fixed_total,
        "normalized_paths": normalized_paths,
        "note": case.note,
    })

    assert case_id_hits == case_id_total, (
        f"{case.name}: {case_id_hits}/{case_id_total} positions ID correctement détectées — "
        f"templates obtenus: {normalized_paths}"
    )
    assert case_fixed_hits == case_fixed_total, (
        f"{case.name}: {case_fixed_hits}/{case_fixed_total} segments fixes préservés (faux positifs) — "
        f"templates obtenus: {normalized_paths}"
    )


class TestSingleExampleFallback:
    """A single observed URL — no sibling to compare against. The GROUP
    step specifically must not call the LLM or force a decision from
    nonexistent cross-request evidence (checked via stats + source !=
    "groq_group"). This does NOT mean the final confidence has to stay
    low: normalize_path()'s pre-existing single-segment fallback
    (semantic_normalizer.py) is a separate mechanism that reasons about
    one URL in isolation and can legitimately resolve it with high
    confidence even without siblings — that's a different, already
    existing code path, not what this test is about."""

    def test_single_example_stays_uncertain(self):
        # Snapshot instead of reset_stats(): a global reset here would wipe
        # out the counters accumulated by every test_recall_case that ran
        # before this one, corrupting the final session-wide report.
        before = group_normalizer.get_stats().fallback_single_example
        entries = [TrafficEntry(
            method="GET",
            url="https://example.com/api/widgets/wgt_omega_099",
            path="/api/widgets/wgt_omega_099",
        )]
        endpoints = normalize_entries(entries, use_ai=True, deduplicate=False)

        after = group_normalizer.get_stats().fallback_single_example
        assert after == before + 1, (
            "expected the group step to recognize it has no sibling to compare "
            "against and skip the group LLM call entirely"
        )

        params = endpoints[0].path_parameters
        assert params, "expected the ambiguous segment to still be flagged as a parameter"
        param = params[0]
        assert param.source != "groq_group", (
            f"the group LLM was never called for this case (no sibling to compare against) — "
            f"it must not appear as the source, got source={param.source!r}"
        )
        print(
            f"\n[single_example] normalized={endpoints[0].normalized_path!r} "
            f"source={param.source} confidence={param.confidence}"
        )


def test_zzz_print_summary_report():
    """
    Declared last in the file on purpose: pytest collects/runs a module's
    tests in declaration order by default, so this only sees a fully
    populated _TALLY if every test_recall_case/TestSingleExampleFallback
    above it already ran. The "zzz" prefix is just a visual marker of that
    ordering dependency, not what enforces it.
    """
    stats = group_normalizer.get_stats()
    total_cases = len(_TALLY.case_results)
    passed_cases = sum(1 for r in _TALLY.case_results if r["passed"])
    recall = _TALLY.id_hits / _TALLY.id_total if _TALLY.id_total else float("nan")
    fp_rate = (
        (_TALLY.fixed_total - _TALLY.fixed_hits) / _TALLY.fixed_total
        if _TALLY.fixed_total else float("nan")
    )

    lines = [
        "",
        "=" * 78,
        "RAPPORT — Recall de détection d'ID dans les URLs (rules + LLM groupé)",
        "=" * 78,
        f"Cas testés            : {total_cases}",
        f"Cas passés            : {passed_cases}/{total_cases}",
        f"Recall ID (global)    : {_TALLY.id_hits}/{_TALLY.id_total} = {recall:.1%}",
        f"Faux positifs (fixes) : {_TALLY.fixed_total - _TALLY.fixed_hits}/{_TALLY.fixed_total} = {fp_rate:.1%}",
        "-" * 78,
        f"Appels LLM de groupe déclenchés : {stats.llm_calls}",
        f"Groupes résolus par les règles seules : {stats.groups_needing_llm - stats.llm_calls - stats.fallback_single_example}",
        f"Fallbacks (exemple unique)       : {stats.fallback_single_example}",
        f"Fallbacks (réponse LLM invalide) : {stats.fallback_invalid_response}",
        "-" * 78,
        "Détail par cas:",
    ]
    for r in _TALLY.case_results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(
            f"  [{status}] {r['name']:<35} id={r['id_hits']}/{r['id_total']} "
            f"fixed={r['fixed_hits']}/{r['fixed_total']}"
        )
        if not r["passed"]:
            lines.append(f"         templates obtenus: {r['normalized_paths']}")
        if r["note"]:
            lines.append(f"         note: {r['note']}")
    lines.append("=" * 78)

    report = "\n".join(lines)
    print(report)
