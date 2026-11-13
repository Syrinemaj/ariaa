"""T3 — Entonnoir du pipeline sur 3 fichiers HAR reels (petit/moyen/gros).

Appelle directement les fonctions de production : parse_har_file -> clean_traffic
-> score_entries(use_ai=True, arbitrage LLM reel sur la zone grise seulement)
-> normalize_entries(use_ai=False dans cette passe -- voir note dans le resume).

Cout : approuve par l'utilisateur pour le volet score_entries (~96 appels sur le
gros HAR, ~0,006 $ estime). La normalisation est lancee en use_ai=False (gratuite)
dans cette passe ; si des parametres restent non resolus, un complement avec
use_ai=True sera propose separement avec sa propre estimation de cout.
"""
import csv
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text

from app.ingestion.har_parser import parse_har_file
from app.ingestion.traffic_cleaner import clean_traffic
from app.ingestion.noise_scoring import score_entries
from app.normalization.service import normalize_entries

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "evaluation" / "results" / "report"

HARS = {
    "petit": ROOT / "tests" / "fixtures" / "example_api_traffic.har",
    "moyen": ROOT / "tests" / "fixtures" / "mock_traffic.har",
    "gros": ROOT / "data" / "uploads" / "foryou-hra4u-final.har",
}

DB_URL = "postgresql://aria10:aria10dev@localhost:5432/aria10"


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def llm_usage_since(engine, since_iso: str) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT COUNT(*) AS n, COALESCE(SUM(total_tokens),0) AS tok, "
                 "COALESCE(SUM(estimated_cost_usd),0) AS cost "
                 "FROM llm_calls WHERE called_at >= :since"),
            {"since": since_iso},
        ).fetchone()
    return {"appels_llm": row.n, "tokens": int(row.tok), "cout_usd": float(row.cost)}


def run_one(name: str, path: Path, engine) -> dict:
    t_start_iso = datetime.now(timezone.utc).isoformat()
    t0 = time.perf_counter()

    raw = parse_har_file(str(path))
    hard = clean_traffic(raw)
    scored = score_entries(hard, use_ai=True)  # arbitrage LLM reel -- approuve

    kept = [e for e in scored if e.is_api_candidate]
    decisions = {}
    for e in scored:
        decisions[e.decision] = decisions.get(e.decision, 0) + 1

    endpoints = normalize_entries(kept, use_ai=False, deduplicate=True)

    t1 = time.perf_counter()
    usage = llm_usage_since(engine, t_start_iso)

    return {
        "har": name, "fichier": str(path.relative_to(ROOT)), "taille_octets": path.stat().st_size,
        "entrees_brutes": len(raw), "apres_filtre_dur": len(hard),
        "decisions": decisions,
        "endpoints_apres_normalisation_dedup": len(endpoints),
        "duree_s": round(t1 - t0, 2),
        "llm": usage,
        "endpoints": [{"method": ep.method, "path": ep.normalized_path, "canonical_key": ep.canonical_key}
                      for ep in endpoints],
    }


def main() -> None:
    engine = create_engine(DB_URL)
    results = []
    for name, path in HARS.items():
        print(f"-- {name} ({path.name}) --")
        r = run_one(name, path, engine)
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "endpoints"}, indent=2, ensure_ascii=False))

    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "modele_llm": "amazon.nova-lite-v1:0 (BEDROCK_MODEL par defaut)",
        "note": "normalize_entries lance en use_ai=False dans cette passe (gratuit) ; "
                "complement use_ai=True a proposer separement si necessaire",
        "runs": [{k: v for k, v in r.items() if k != "endpoints"} for r in results],
    }
    (OUT_DIR / "T3_entonnoir_pipeline.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    with open(OUT_DIR / "T3_entonnoir_pipeline.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["har", "entrees_brutes", "apres_filtre_dur", "kept_by_rules", "rejected_by_rules",
                    "rejected_no_client", "ambiguous", "endpoints_final", "appels_llm", "tokens", "cout_usd"])
        for r in results:
            d = r["decisions"]
            w.writerow([r["har"], r["entrees_brutes"], r["apres_filtre_dur"],
                        d.get("kept_by_rules", 0), d.get("rejected_by_rules", 0),
                        d.get("rejected_no_client", 0), d.get("ambiguous", 0),
                        r["endpoints_apres_normalisation_dedup"],
                        r["llm"]["appels_llm"], r["llm"]["tokens"], r["llm"]["cout_usd"]])

    for r in results:
        with open(OUT_DIR / f"T3_endpoints_{r['har']}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["method", "path", "canonical_key", "correct (o/n)", "commentaire"])
            for ep in r["endpoints"]:
                w.writerow([ep["method"], ep["path"], ep["canonical_key"], "", ""])

    print("\n=== RESUME ===")
    for r in results:
        print(f"{r['har']:6s} | brutes={r['entrees_brutes']:4d} | filtre_dur={r['apres_filtre_dur']:4d} | "
              f"endpoints={r['endpoints_apres_normalisation_dedup']:4d} | "
              f"LLM: {r['llm']['appels_llm']} appels, {r['llm']['tokens']} tokens, {r['llm']['cout_usd']:.4f} $")


if __name__ == "__main__":
    main()
