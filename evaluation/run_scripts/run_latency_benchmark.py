"""ARIA-EVAL: wall-clock latency benchmark — times real Bedrock Converse
calls per model on the same fixed payload set, independent of the quality
scoring in aggregate.py (latency isn't part of the weighted ranking; this
is a separate signal to weigh alongside it).

Reuses sequence_reorder_golden_dataset.json (13 cases, small max_tokens=400)
through the real _REORDER_SYSTEM/_REORDER_SCHEMA — same production code path
as run_sequence_reorder_eval.py — purely for a small, cheap, already-
validated payload set; the quality results from that run are not reused
here, only the payload shape.

THIS COSTS REAL TOKENS (small — 13 cases x N models, max_tokens=400).

    python -m evaluation.run_scripts.run_latency_benchmark \\
        --models deepseek.v3.2,amazon.nova-lite-v1:0
"""
from __future__ import annotations

import argparse
import json
import os
import time
from typing import List

from app.ai.bedrock_client import BedrockClient
from app.workflows.sequence_builder import _REORDER_SCHEMA, _REORDER_SYSTEM

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
GOLDEN_DATASET_PATH = os.path.join(_EVAL_ROOT, "golden_dataset", "sequence_reorder_golden_dataset.json")


def _load_payloads() -> List[dict]:
    with open(GOLDEN_DATASET_PATH, encoding="utf-8") as f:
        cases = json.load(f)
    return [
        {"steps": [
            {"key": s["key"], "method": s["method"], "path": s["path"], "summary": s.get("summary") or ""}
            for s in case["steps"]
        ]}
        for case in cases
    ]


def _percentile(sorted_vals: List[float], pct: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * pct), len(sorted_vals) - 1)
    return sorted_vals[idx]


def run_for_model(model_id: str, payloads: List[dict]) -> dict:
    client = BedrockClient(model=model_id)
    latencies_ms: List[float] = []
    errors = 0

    for payload in payloads:
        start = time.perf_counter()
        try:
            client.structured_chat(
                system_prompt=_REORDER_SYSTEM,
                user_payload=payload,
                json_schema=_REORDER_SCHEMA,
                task_name="latency_benchmark",
                max_tokens=400,
            )
        except Exception as exc:
            errors += 1
            print(f"  ⚠ erreur sur un appel ({type(exc).__name__}) — exclu des stats de latence")
            continue
        finally:
            latencies_ms.append((time.perf_counter() - start) * 1000)

    latencies_sorted = sorted(latencies_ms)
    return {
        "model": model_id,
        "calls": len(payloads),
        "errors": errors,
        "mean_ms": sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0,
        "p50_ms": _percentile(latencies_sorted, 0.50),
        "p95_ms": _percentile(latencies_sorted, 0.95),
        "min_ms": min(latencies_ms) if latencies_ms else 0.0,
        "max_ms": max(latencies_ms) if latencies_ms else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", required=True, help="IDs de modèle Bedrock séparés par des virgules")
    args = parser.parse_args()

    payloads = _load_payloads()
    print(f"{len(payloads)} appels par modèle (payload fixe, réutilisé pour chaque modèle)\n")

    rows = []
    for model_id in [m.strip() for m in args.models.split(",")]:
        print(f"▶ {model_id} ...")
        row = run_for_model(model_id, payloads)
        rows.append(row)
        print(
            f"  moyenne={row['mean_ms']:.0f}ms  P50={row['p50_ms']:.0f}ms  "
            f"P95={row['p95_ms']:.0f}ms  min={row['min_ms']:.0f}ms  max={row['max_ms']:.0f}ms  "
            f"erreurs={row['errors']}/{row['calls']}\n"
        )

    print("═" * 70)
    print(f"{'Modèle':38s} {'Moyenne':>9s} {'P50':>8s} {'P95':>8s}")
    print("-" * 70)
    for row in sorted(rows, key=lambda r: r["mean_ms"]):
        print(f"{row['model']:38s} {row['mean_ms']:>7.0f}ms {row['p50_ms']:>6.0f}ms {row['p95_ms']:>6.0f}ms")


if __name__ == "__main__":
    main()
