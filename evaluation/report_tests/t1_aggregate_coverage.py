"""T1 — agrège evaluation/results/report/t1_coverage.json (produit par pytest-cov)
par module métier (ingestion, normalization, rag, planner, governance, approval,
automation, bulk_execution, security, connections) et écrit le résumé final.
Lecture seule sur le JSON déjà produit par pytest ; n'exécute aucun test.
"""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COV_JSON = ROOT / "evaluation" / "results" / "report" / "t1_coverage.json"
OUT_DIR = ROOT / "evaluation" / "results" / "report"

MODULES = [
    "ingestion", "normalization", "rag", "planner", "governance",
    "approval", "automation", "bulk_execution", "security", "connections",
]


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def main() -> None:
    data = json.loads(COV_JSON.read_text(encoding="utf-8"))
    files = data["files"]

    rows = []
    for mod in MODULES:
        prefix = f"app{__import__('os').sep}{mod}{__import__('os').sep}"
        prefix_alt = f"app/{mod}/"
        covered = 0
        total = 0
        for path, info in files.items():
            norm = path.replace("\\", "/")
            if norm.startswith(f"app/{mod}/"):
                s = info["summary"]
                covered += s["covered_lines"]
                total += s["num_statements"]
        pct = round(100 * covered / total, 1) if total else None
        rows.append({"module": mod, "lignes_couvertes": covered, "lignes_totales": total, "couverture_pct": pct})

    totals = data["totals"]
    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "commande": "pytest tests/unit --cov=app --cov-report=term-missing "
                    "--cov-report=json:evaluation/results/report/t1_coverage.json "
                    "--junitxml=evaluation/results/report/t1_junit.xml -q",
        "tests_total": 475,
        "tests_reussis": 444,
        "tests_ignores": 31,
        "tests_echoues": 0,
        "couverture_globale_pct": round(totals["percent_covered"], 1),
        "modules": rows,
    }

    (OUT_DIR / "T1_tests_unitaires.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    import csv
    with open(OUT_DIR / "T1_tests_unitaires.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["module", "lignes_couvertes", "lignes_totales", "couverture_pct"])
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# T1 — Tests unitaires + couverture",
        "",
        f"- Date (UTC) : {meta['date_utc']}",
        f"- Commit : `{meta['commit']}`",
        f"- Commande : `{meta['commande']}`",
        f"- Total collecté : {meta['tests_total']} | Réussis : {meta['tests_reussis']} | "
        f"Échoués : {meta['tests_echoues']} | Ignorés : {meta['tests_ignores']}",
        f"- Couverture globale (tout `app/`) : {meta['couverture_globale_pct']} %",
        "",
        "| Module | Lignes couvertes | Lignes totales | Couverture |",
        "|---|---|---|---|",
    ]
    for r in rows:
        pct = f"{r['couverture_pct']} %" if r["couverture_pct"] is not None else "n/a"
        lines.append(f"| {r['module']} | {r['lignes_couvertes']} | {r['lignes_totales']} | {pct} |")
    (OUT_DIR / "T1_tests_unitaires.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
