"""T4 — Reverifie la couche de regles seule (sans LLM) du filtrage HAR contre
evaluation/golden_dataset/traffic_classification_golden_dataset.json (30 cas),
en appelant directement les fonctions de production (app.ingestion.noise_scoring,
heuristic_filter, payload_classifier). use_ai=False : aucun appel reseau/LLM.
"""
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.models import TrafficEntry
from app.ingestion.noise_scoring import score_entry

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "evaluation" / "golden_dataset" / "traffic_classification_golden_dataset.json"
OUT_DIR = ROOT / "evaluation" / "results" / "report"

EXPECTED = {"precision": 0.667, "rappel": 1.000, "f1": 0.800, "faux_positifs": 7}


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def main() -> None:
    cases = json.loads(GOLDEN.read_text(encoding="utf-8"))

    rows = []
    tp = fp = fn = tn = 0
    gray = 0
    for case in cases:
        entry = TrafficEntry(
            method=case["method"],
            url=case["url"],
            path=case["path"],
            status=case["status"],
            mime_type=case.get("mime_type"),
            request_headers=case.get("request_headers", {}),
            response_headers=case.get("response_headers", {}),
            request_body=case.get("request_body"),
            response_body=case.get("response_body"),
        )
        scored = score_entry(entry, use_ai=False, client=None)
        expected_keep = case["expected"]["should_keep"]

        decided = scored.decision in ("kept_by_rules", "rejected_by_rules")
        predicted_keep = scored.decision == "kept_by_rules"

        if decided:
            if predicted_keep and expected_keep:
                tp += 1
            elif predicted_keep and not expected_keep:
                fp += 1
            elif not predicted_keep and expected_keep:
                fn += 1
            else:
                tn += 1
        else:
            gray += 1

        rows.append({
            "case_id": case["case_id"], "strata": case["strata"],
            "expected_should_keep": expected_keep, "decision": scored.decision,
            "combined_score": round(scored.relevance_score, 3),
        })

    decided_total = tp + fp + fn + tn
    precision = round(tp / (tp + fp), 3) if (tp + fp) else None
    recall = round(tp / (tp + fn), 3) if (tp + fn) else None
    f1 = round(2 * precision * recall / (precision + recall), 3) if precision and recall and (precision + recall) else None

    measured = {"precision": precision, "rappel": recall, "f1": f1, "faux_positifs": fp}

    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "commande": "python evaluation/report_tests/t4_rules_only_reeval.py",
        "modele_llm": None,
        "modele_embedding": None,
        "note": "use_ai=False : aucun appel reseau/LLM pour cette mesure",
        "cas_total": len(cases),
        "cas_decides_par_regles": decided_total,
        "cas_zone_grise": gray,
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "mesure": measured,
        "attendu": EXPECTED,
        "ecarts": {k: (None if measured[k] is None else round(measured[k] - EXPECTED[k], 3)) for k in EXPECTED},
    }

    (OUT_DIR / "T4_filtrage_har_golden.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(OUT_DIR / "T4_filtrage_har_golden.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case_id", "strata", "expected_should_keep", "decision", "combined_score"])
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# T4 — Filtrage HAR, golden dataset (couche regles seule, use_ai=False)",
        "",
        f"- Date (UTC) : {meta['date_utc']}",
        f"- Commit : `{meta['commit']}`",
        f"- Cas totaux : {meta['cas_total']} | decides par les regles : {decided_total} | zone grise : {gray}",
        "",
        "| Metrique | Mesure | Attendu | Ecart |",
        "|---|---|---|---|",
    ]
    for k in EXPECTED:
        lines.append(f"| {k} | {measured[k]} | {EXPECTED[k]} | {meta['ecarts'][k]} |")
    (OUT_DIR / "T4_filtrage_har_golden.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
