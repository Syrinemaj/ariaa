"""ARIA-EVAL: large-scale structural stress test for URL normalization.

Complementary to normalization_golden_dataset.json (55 hand-verified cases
with exact ground truth) — this generates ~400 synthetic URLs across ~30
endpoint families and many ID formats, then checks STRUCTURAL INVARIANTS
that hold regardless of any single expected answer (no per-case ground
truth needed at this volume):

  - catalog compression (N raw URLs -> M distinct endpoints, sanity range)
  - raw ID leak count (must always be 0 — Bug 2 regression guard)
  - naming consistency (must always be 100% — same position, same name)
  - confidence distribution (health signal, not pass/fail)
  - source distribution (real rules-vs-LLM ratio at volume)
  - lowest-confidence sample, for targeted manual review

No hand-verified expected_names here — that doesn't scale to hundreds of
cases. Deterministic generation (no LLM), so the input is reproducible
across runs even though it's synthetic.

    python -m evaluation.run_scripts.run_normalization_stress_test
    python -m evaluation.run_scripts.run_normalization_stress_test --with-ai

# ARIA-EVAL: evaluation/ folder restructuring (Phase 2) — this file used to
# be evaluation/run_normalization_stress_test.py. Moved into run_scripts/;
# output CSVs now write into evaluation/results/. No behavior change.
"""
from __future__ import annotations

import csv
import os
import re
import sys
import uuid
from typing import Dict, List, Set, Tuple

from app.ingestion.models import TrafficEntry
from app.normalization.deduplication import deduplicate_endpoints
from app.normalization.service import normalize_entries

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")
RESULTS_CSV_PATH = os.path.join(_RESULTS_DIR, "normalization_stress_results.csv")
LOW_CONFIDENCE_CSV_PATH = os.path.join(_RESULTS_DIR, "normalization_stress_low_confidence.csv")
CATALOG_CSV_PATH = os.path.join(_RESULTS_DIR, "normalization_stress_catalog_deduplicated.csv")

_PLACEHOLDER_RE = re.compile(r"^\{.+\}$")
_RAW_ID_LEAK_RE = re.compile(r"^[a-z]+_\d+_id$")


# ── Génération synthétique (~400 URLs, ~30 familles, déterministe) ───────────

def _uuid(seed: int) -> str:
    return str(uuid.UUID(int=seed * 1_000_003 + 42))


def generate_urls() -> List[Tuple[str, str]]:
    """Retourne une liste de (method, path). Volontairement diverse :
    tous les formats d'ID connus, plusieurs domaines métier, et des pièges
    (Bug 1 : ressources sœurs ; Bug 2 : action sœur après un ID ; slugs
    purs ; mots-statuts ; segments de version)."""
    urls: List[Tuple[str, str]] = []

    def add(method: str, path: str) -> None:
        urls.append((method, path))

    # 1. HR employees — prefixed_resource_id (20)
    for i in range(1, 21):
        add("GET", f"/hr/employees/emp_{100 + i}")

    # 2. HR departments x employees — 2 niveaux imbriqués (15 combos)
    for d in range(1, 6):
        for e in range(1, 4):
            add("GET", f"/hr/departments/dept_{d}0/employees/emp_{d}{e}0")

    # 3-4. HR contract vs salary — piège Bug 2 (15 + 15)
    for i in range(1, 16):
        add("POST", f"/hr/employees/emp_{300 + i}/contract")
        add("POST", f"/hr/employees/emp_{300 + i}/salary")

    # 5. HR employees vs departments (racine) — piège Bug 1
    for _ in range(5):
        add("GET", "/hr/employees")
    for _ in range(5):
        add("GET", "/hr/departments")

    # 6. Shop products — prefixed (20)
    for i in range(1, 21):
        add("GET", f"/shop/products/prod_{i}")

    # 7. Shop products — UUID (10)
    for i in range(10):
        add("GET", f"/shop/products/{_uuid(i)}")

    # 8. Shop carts (15)
    for i in range(7001, 7016):
        add("GET", f"/shop/carts/cart_{i}")

    # 9. Shop cart items — 2 niveaux (15)
    for i in range(7001, 7011):
        for j in range(1, 2):
            add("GET", f"/shop/carts/cart_{i}/items/item_{j}")

    # 10. Shop orders (20)
    for i in range(3001, 3021):
        add("GET", f"/shop/orders/ord_{i}")

    # 11-12. Shop orders cancel vs refund — piège Bug 2 (15 + 15)
    for i in range(3001, 3016):
        add("POST", f"/shop/orders/ord_{i}/cancel")
        add("POST", f"/shop/orders/ord_{i}/refund")

    # 13. Auth login/logout/register — piège Bug 1, pas d'ID (5 chacun)
    for _ in range(5):
        add("POST", "/auth/login")
    for _ in range(5):
        add("POST", "/auth/logout")
    for _ in range(5):
        add("POST", "/auth/register")

    # 14. Auth users (20)
    for i in range(501, 521):
        add("GET", f"/auth/users/usr_{i}")

    # 15. Auth users roles (15)
    for i in range(501, 516):
        add("GET", f"/auth/users/usr_{i}/roles")

    # 16. Auth sessions (15)
    for i in range(9001, 9016):
        add("DELETE", f"/auth/sessions/sess_{i}")

    # 17. Blog posts — slug + marqueur numérique (20)
    titles = ["guide-python", "astuces-normalisation", "top-10-api", "retour-experience",
              "tutoriel-fastapi", "comparatif-outils", "bonnes-pratiques", "cas-usage",
              "architecture-rules-first", "pipeline-har", "detection-id", "llm-fallback",
              "regex-avancees", "cardinalite-variance", "workflow-detection", "rag-pgvector",
              "celery-redis", "postgresql-async", "structured-output", "confidence-scoring"]
    for i, title in enumerate(titles):
        add("GET", f"/blog/posts/{title}-{400 + i}")

    # 18. Blog posts — slug PUR sans marqueur — piège compromis accepté (10)
    pure_titles = ["mon-titre-darticle", "une-histoire-sans-fin", "reflexions-du-jour",
                   "notes-de-voyage", "recette-facile", "avis-personnel", "chronique-hebdo",
                   "billet-invite", "analyse-approfondie", "retrospective-annuelle"]
    for title in pure_titles:
        add("GET", f"/blog/posts/{title}")

    # 19. Blog categories/tags/authors (racine) — piège Bug 1 (5 chacun)
    for _ in range(5):
        add("GET", "/blog/categories")
    for _ in range(5):
        add("GET", "/blog/tags")
    for _ in range(5):
        add("GET", "/blog/authors")

    # 20. Billing charges — Stripe-style (15)
    stripe_suffixes = ["1AbCdEfGhIjKlMn", "9XyZaBcDeFgHiJk", "A1b2C3D4E5f6G7h", "Zz9Yy8Xx7Ww6Vv",
                        "Qw3Er4Ty5Ui6Op", "Ml2Nb3Vc4Xz5Aq", "Rt6Yu7Io8Pa9Sd", "Fg1Hj2Kl3Zx4Cv",
                        "B5N6M7Q8W9E0Rt", "T1y2U3i4O5p6As", "D7f8G9h0J1k2Lz", "X3c4V5b6N7m8Qw",
                        "E9r0T1y2U3i4Op", "As5Df6Gh7Jk8Lz", "Zx9Cv0Bn1Mq2We"]
    for suffix in stripe_suffixes:
        add("GET", f"/billing/charges/ch_{suffix}")

    # 21. Billing customers — Stripe-style, préfixe différent (15)
    for i, suffix in enumerate(stripe_suffixes):
        add("GET", f"/billing/customers/cus_{suffix[:8 + (i % 4)]}")

    # 22. Chain transactions — hex 0x (15)
    hex_vals = ["1a2b3c4d5e", "deadbeef01", "cafebabe99", "0123456789abcdef", "ff00ff00ff",
                "aabbccddee", "1122334455", "9988776655", "fedcba9876", "0f1e2d3c4b",
                "abcdef0123", "3456789abc", "def0123456", "789abcdef0", "23456789ab"]
    for h in hex_vals:
        add("GET", f"/chain/transactions/0x{h}")

    # 23. Support tickets — code métier structuré (15)
    for i in range(1, 16):
        add("GET", f"/support/tickets/TCK-2024-{1000 + i}")

    # 24. Finance invoices (15)
    for i in range(1, 16):
        add("GET", f"/finance/invoices/INV-2024-{2000 + i}")

    # 25. Webhooks — hash hex court (15)
    hex_short = ["9f2a7b", "ab12cd", "3e7f9a", "1c4d8e", "6b2f5a", "de9c31", "7a4b2e", "f19c6d",
                 "2e8a4c", "b5d7f1", "48c2a9", "e3f6b8", "9a1d4c", "c7e2f9", "5d8b3a"]
    for h in hex_short:
        add("GET", f"/webhooks/{h}")

    # 26. Catalog items — code métier générique inconnu (15)
    for i in range(1, 16):
        add("GET", f"/catalog/items/XYZ-{4000 + i}")

    # 27. Reports — mots-statuts qui varient — piège compromis accepté (4 valeurs)
    for status in ["pending", "active", "archived", "completed"]:
        add("GET", f"/reports/{status}")

    # 28. API versionné — piège segment statique (v1/v2/v3, ne doit jamais devenir un param)
    for v in ["v1", "v2", "v3"]:
        add("GET", f"/api/{v}/employees")

    # 29. Analytics events — clé composite (15)
    for i in range(1, 16):
        add("GET", f"/analytics/events/{100 + i}_{200 + i}")

    # 30. Inventory SKUs (15)
    sku_suffixes = ["1234AB", "9987ZZ", "5566CD", "7788EF", "3344GH", "1122IJ", "9900KL",
                     "6655MN", "4433OP", "2211QR", "8899ST", "5577UV", "3355WX", "1199YZ", "7733AA"]
    for suffix in sku_suffixes:
        add("GET", f"/inventory/skus/SKU-{suffix}")

    # 31. Gadgets — préfixe inconnu, confidence basse attendue (15)
    for i in range(1, 16):
        add("GET", f"/gadgets/items/xqz_{700 + i}")

    return urls


# ── Runner ────────────────────────────────────────────────────────────────

def _segments(path: str) -> List[str]:
    return [s for s in path.split("/") if s]


def run_stress_test(use_ai: bool = False) -> None:
    urls = generate_urls()
    entries = [
        TrafficEntry(method=m, url=f"https://example.com{p}", path=p)
        for m, p in urls
    ]

    endpoints = normalize_entries(entries, use_ai=use_ai, deduplicate=False)

    distinct_templates = {ep.normalized_path for ep in endpoints}
    canonical_keys = {ep.canonical_key for ep in endpoints}

    leaked: List[Tuple[str, str]] = []
    param_rows: List[dict] = []
    names_by_key_position: Dict[Tuple[str, int], Set[str]] = {}
    source_counter: Dict[str, int] = {}
    confidence_buckets = {"<0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, ">=0.9": 0}

    for ep in endpoints:
        segs = _segments(ep.normalized_path)
        placeholder_positions = [i for i, s in enumerate(segs) if _PLACEHOLDER_RE.match(s)]
        for pos, param in zip(placeholder_positions, ep.path_parameters):
            source_counter[param.source] = source_counter.get(param.source, 0) + 1

            if param.confidence < 0.5:
                confidence_buckets["<0.5"] += 1
            elif param.confidence < 0.7:
                confidence_buckets["0.5-0.7"] += 1
            elif param.confidence < 0.9:
                confidence_buckets["0.7-0.9"] += 1
            else:
                confidence_buckets[">=0.9"] += 1

            if _RAW_ID_LEAK_RE.match(param.name):
                leaked.append((ep.original_path, param.name))

            key = (ep.canonical_key, pos)
            names_by_key_position.setdefault(key, set()).add(param.name)

            param_rows.append({
                "original_path": ep.original_path,
                "normalized_path": ep.normalized_path,
                "position": pos,
                "raw_value": param.raw_value,
                "name": param.name,
                "type": param.type,
                "source": param.source,
                "confidence": param.confidence,
            })

    consistency_violations = sum(1 for names in names_by_key_position.values() if len(names) > 1)
    consistency_rate = (
        (len(names_by_key_position) - consistency_violations) / len(names_by_key_position)
        if names_by_key_position else 0.0
    )

    total_source = sum(source_counter.values())
    llm_calls = source_counter.get("groq_group", 0) + source_counter.get("groq", 0)
    llm_pct = llm_calls / total_source if total_source else 0.0

    print("══ STRESS TEST — NORMALISATION URL (grande échelle) ══")
    print(f"Mode                     : {'use_ai=True' if use_ai else 'use_ai=False (déterministe)'}")
    print(f"URLs générées            : {len(urls)}")
    print(f"Endpoints distincts      : {len(distinct_templates)} (templates) / {len(canonical_keys)} (canonical_key)")
    print(f"Taux de compression      : {len(urls) / len(distinct_templates):.1f}x (URLs par endpoint distinct, en moyenne)")
    print(f"Fuite d'ID brut          : {len(leaked)} (doit être 0)")
    print(f"Cohérence de nommage     : {consistency_rate:.2%} ({consistency_violations} position(s) incohérente(s) sur {len(names_by_key_position)})")
    print(f"Taux de fallback LLM     : {llm_pct:.1%}" + ("" if use_ai else "  (toujours 0% en mode déterministe — relancer avec --with-ai)"))

    print("\n── Distribution de confidence (tous paramètres détectés) ──")
    total_params = sum(confidence_buckets.values())
    for bucket, count in confidence_buckets.items():
        pct = count / total_params if total_params else 0.0
        print(f"  {bucket:10s}: {count:4d} ({pct:.1%})")

    print("\n── Répartition par source ──")
    for source, count in sorted(source_counter.items(), key=lambda kv: -kv[1]):
        pct = count / total_source if total_source else 0.0
        print(f"  {source:25s}: {count:4d} ({pct:.1%})")

    if leaked:
        print("\n── ⚠ Fuites détectées (à corriger) ──")
        for path, name in leaked:
            print(f"  {path} -> {name}")

    # CSV complet
    with open(RESULTS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "original_path", "normalized_path", "position", "raw_value", "name", "type", "source", "confidence",
        ])
        writer.writeheader()
        writer.writerows(param_rows)

    # CSV des N cas à confidence la plus basse — échantillon pour revue manuelle ciblée
    lowest = sorted(param_rows, key=lambda r: r["confidence"])[:30]
    with open(LOW_CONFIDENCE_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "original_path", "normalized_path", "raw_value", "name", "type", "source", "confidence",
        ])
        writer.writeheader()
        for r in lowest:
            writer.writerow({k: r[k] for k in writer.fieldnames})

    # ARIA-EVAL: `endpoints` ci-dessus est volontairement non-déduplique
    # (une ligne par URL brute — nécessaire pour compter les positions/
    # sources/confidences individuellement). Ici on applique la VRAIE
    # déduplication du pipeline (deduplicate_endpoints(), utilisée par
    # défaut en production) sur les mêmes 447 URLs, pour montrer le
    # catalogue final tel qu'il serait réellement stocké.
    deduplicated = deduplicate_endpoints(endpoints)
    with open(CATALOG_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "canonical_key", "method", "normalized_path", "source_count", "example_original_url",
        ])
        writer.writeheader()
        for ep in sorted(deduplicated, key=lambda e: e.canonical_key):
            writer.writerow({
                "canonical_key": ep.canonical_key,
                "method": ep.method,
                "normalized_path": ep.normalized_path,
                "source_count": ep.source_count,
                "example_original_url": ep.original_url,
            })

    print(f"\nRésultats complets            → {RESULTS_CSV_PATH}")
    print(f"Échantillon confidence basse   → {LOW_CONFIDENCE_CSV_PATH} ({len(lowest)} cas à revoir manuellement)")
    print(f"Catalogue final (dédupliqué)   → {CATALOG_CSV_PATH} ({len(deduplicated)} endpoints, {sum(e.source_count for e in deduplicated)} URLs fusionnées)")


if __name__ == "__main__":
    run_stress_test(use_ai="--with-ai" in sys.argv)
