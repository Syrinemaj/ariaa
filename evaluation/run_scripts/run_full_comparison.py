"""ARIA-EVAL: cross-task ranking — reads whichever summary_<task>.json files
are currently in evaluation/results/ (written by each run_*_eval.py's
run_comparison() at the end of its own run) and combines them into ONE
weighted ranking per model, using the weights and per-task quality formulas
defined in evaluation/aggregate.py.

This does NOT call any LLM and costs nothing — it only aggregates results
that were already produced (and paid for) by prior runs of the individual
task harnesses. Run it any time after running one or more of:

    run_traffic_classification_eval.py, run_workflow_grouping_eval.py,
    run_endpoint_understanding_eval.py, run_sequence_reorder_eval.py,
    run_workflow_description_eval.py, run_domain_canonicalization_eval.py

    python -m evaluation.run_scripts.run_full_comparison
"""
from __future__ import annotations

import csv
import os

from evaluation.aggregate import TASK_CONFIG, compute_rankings

_RUN_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_EVAL_ROOT = os.path.dirname(_RUN_SCRIPTS_DIR)
_RESULTS_DIR = os.path.join(_EVAL_ROOT, "results")


def main() -> None:
    rankings = compute_rankings()

    if not rankings:
        print(
            "Aucun summary_<task>.json trouvé dans evaluation/results/ — "
            "lance d'abord au moins un run_*_eval.py --models ... --budget ..."
        )
        return

    present_tasks = {t for r in rankings for t in r["per_task_quality"] if r["per_task_quality"][t] is not None}
    missing_tasks = [tid for tid in TASK_CONFIG if tid not in present_tasks]

    print(f"\n{'=' * 78}\n══ CLASSEMENT FINAL — {len(present_tasks)}/{len(TASK_CONFIG)} tâches couvertes ══\n{'=' * 78}")
    if missing_tasks:
        print("Tâches non incluses (aucun summary trouvé) :")
        for tid in missing_tasks:
            print(f"  - {TASK_CONFIG[tid]['label']} (poids {TASK_CONFIG[tid]['weight']}/100)")
        print()

    header = f"{'Modèle':38s} {'Score pondéré':>14s} {'Tâches (poids)':>15s} {'Coût total $':>13s} {'Qualité/$':>10s}"
    print(header)
    print("-" * len(header))
    for r in rankings:
        qpd = f"{r['quality_per_dollar']:.2f}" if r["quality_per_dollar"] is not None else "n/a"
        print(
            f"{r['model']:38s} {r['overall_score']:>13.1%} {r['tasks_covered']:>11.0f}/100 "
            f"{r['total_cost_usd']:>12.4f}$ {qpd:>10s}"
        )

    print(f"\n{'=' * 78}\nDétail par tâche (score de qualité 0-1, avant application du poids)\n{'=' * 78}")
    task_ids = [t for t in TASK_CONFIG if t in present_tasks]
    sub_header = f"{'Modèle':38s} " + " ".join(f"{tid[:14]:>15s}" for tid in task_ids)
    print(sub_header)
    for r in rankings:
        cells = []
        for tid in task_ids:
            q = r["per_task_quality"].get(tid)
            cells.append(f"{q:>15.1%}" if q is not None else f"{'—':>15s}")
        print(f"{r['model']:38s} " + " ".join(cells))

    if rankings:
        winner = rankings[0]
        print(
            f"\n➜ Meilleur score pondéré : {winner['model']} "
            f"({winner['overall_score']:.1%}, {winner['tasks_covered']}/100 de poids couvert, "
            f"{winner['total_cost_usd']:.4f}$ dépensés sur les tâches incluses)"
        )
        if len(rankings) > 1:
            cheapest_good = min(
                (r for r in rankings if r["overall_score"] >= winner["overall_score"] - 0.05),
                key=lambda r: r["total_cost_usd"],
            )
            if cheapest_good["model"] != winner["model"]:
                print(
                    f"➜ À qualité quasi équivalente (dans -5 pts), le moins cher est : "
                    f"{cheapest_good['model']} ({cheapest_good['overall_score']:.1%}, "
                    f"{cheapest_good['total_cost_usd']:.4f}$)"
                )

    os.makedirs(_RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(_RESULTS_DIR, "full_comparison.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["model", "overall_score", "tasks_covered_weight", "total_cost_usd", "quality_per_dollar"] + task_ids
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rankings:
            row = {
                "model": r["model"],
                "overall_score": f"{r['overall_score']:.4f}",
                "tasks_covered_weight": r["tasks_covered"],
                "total_cost_usd": f"{r['total_cost_usd']:.4f}",
                "quality_per_dollar": f"{r['quality_per_dollar']:.4f}" if r["quality_per_dollar"] is not None else "",
            }
            for tid in task_ids:
                q = r["per_task_quality"].get(tid)
                row[tid] = f"{q:.4f}" if q is not None else ""
            writer.writerow(row)
    print(f"\nClassement exporté → {out_path}")


if __name__ == "__main__":
    main()
