"""T5 -- Evaluation RAG sur le vrai catalogue indexe (run_id du gros HAR,
83 endpoints reels, hr-rich-client/Sopra HR). 25 requetes dans rag_queries.json.

Deux conditions :
  - "sans juge" : appel direct a semantic_search_endpoints (recherche vectorielle
    pure, top_k=5), dans ce process.
  - "avec juge" : appel au vrai endpoint HTTP POST /rag/search (production),
    qui applique systematiquement relevance_judge apres la recherche.

Cout Bedrock : 25 embeddings (requete) x 2 conditions = jusqu'a 50 appels
embedding (le texte de requete est identique dans les deux conditions, un
cache peut en epargner la moitie) + 25 appels au juge (LLM) pour la condition
"avec juge". Tres faible cout (meme ordre de grandeur que T3/T9).
"""
import asyncio
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.ai.base_client import create_embedding_client
from app.rag.retriever import semantic_search_endpoints

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "evaluation" / "results" / "report"
RUN_ID = "06f866a1-d8d6-4900-b3a0-cd3bc02c568c"
DB_URL_ASYNC = "postgresql+asyncpg://aria10:aria10dev@localhost:5432/aria10"
BASE = "http://localhost:8000"


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def _match(result_key: str, expected: list[str]) -> bool:
    return result_key in expected


def recall_at_k(ranked_keys: list[str], expected: list[str], k: int) -> int:
    if not expected:
        return None  # out-of-catalog case, scored separately
    return 1 if any(_match(key, expected) for key in ranked_keys[:k]) else 0


def mrr_contrib(ranked_keys: list[str], expected: list[str]) -> float:
    if not expected:
        return None
    for i, key in enumerate(ranked_keys, start=1):
        if _match(key, expected):
            return 1.0 / i
    return 0.0


async def run_without_judge(queries: list[dict], org_id: str) -> dict:
    engine = create_async_engine(DB_URL_ASYNC)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    client = create_embedding_client()
    out = {}
    async with Session() as db:
        for q in queries:
            results = await semantic_search_endpoints(
                db=db, query=q["query"], client=client, run_id=RUN_ID, org_id=org_id, top_k=5,
            )
            ranked = [f"{r.method} {r.path}" for r in results]
            out[q["id"]] = ranked
    await engine.dispose()
    return out


def run_with_judge(queries: list[dict], token: str) -> dict:
    out = {}
    for q in queries:
        r = requests.post(
            f"{BASE}/rag/search",
            headers={"Authorization": f"Bearer {token}"},
            json={"query": q["query"], "run_id": RUN_ID, "top_k": 5, "score_threshold": 0.0},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        ranked = [f"{res['method']} {res['path']}" for res in data["results"]]
        out[q["id"]] = ranked
    return out


def summarize(queries: list[dict], ranked_by_id: dict) -> dict:
    rows = []
    for q in queries:
        ranked = ranked_by_id.get(q["id"], [])
        r1 = recall_at_k(ranked, q["expected"], 1)
        r5 = recall_at_k(ranked, q["expected"], 5)
        mrr = mrr_contrib(ranked, q["expected"])
        rows.append({"id": q["id"], "lang": q["lang"], "difficulty": q["difficulty"],
                      "recall_at_1": r1, "recall_at_5": r5, "mrr": mrr,
                      "top_result": ranked[0] if ranked else None, "out_of_catalog_empty": (not q["expected"] and not ranked)})

    def agg(rows_subset):
        scored = [r for r in rows_subset if r["recall_at_1"] is not None]
        if not scored:
            return None
        return {
            "n": len(scored),
            "recall_at_1": round(sum(r["recall_at_1"] for r in scored) / len(scored), 3),
            "recall_at_5": round(sum(r["recall_at_5"] for r in scored) / len(scored), 3),
            "mrr": round(sum(r["mrr"] for r in scored) / len(scored), 3),
        }

    return {
        "rows": rows,
        "global": agg(rows),
        "fr": agg([r for r in rows if r["lang"] == "fr"]),
        "en": agg([r for r in rows if r["lang"] == "en"]),
        "out_of_catalog_handled_honestly": next(
            (r["out_of_catalog_empty"] for r in rows if r["id"] == "q25"), None),
    }


def main() -> None:
    import os
    queries = json.loads((ROOT / "evaluation" / "report_tests" / "rag_queries.json").read_text(encoding="utf-8"))

    token = requests.post(f"{BASE}/auth/login", json={
        "email": os.environ["ARIA_ADMIN_EMAIL"], "password": os.environ["ARIA_ADMIN_PASSWORD"],
    }, timeout=10).json()["access_token"]
    me = requests.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=10).json()
    org_id = me["org_id"] if "org_id" in me else None

    without_judge = asyncio.run(run_without_judge(queries, org_id))
    with_judge = run_with_judge(queries, token)

    summary_without = summarize(queries, without_judge)
    summary_with = summarize(queries, with_judge)

    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "run_id": RUN_ID,
        "catalogue": "83 endpoints reels (hr-rich-client, anonymise -- aucune donnee personnelle dans les requetes de test)",
        "sans_juge": summary_without,
        "avec_juge": summary_with,
    }
    (OUT_DIR / "T5_rag_evaluation.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T5 — Evaluation RAG (25 requetes, catalogue reel 83 endpoints)", "",
              f"- Date (UTC) : {meta['date_utc']} | Commit : `{meta['commit']}` | run_id : `{RUN_ID}`", ""]
    for label, summ in [("Sans juge de pertinence (recherche vectorielle seule)", summary_without),
                         ("Avec juge de pertinence (chemin de production reel, /rag/search)", summary_with)]:
        lines.append(f"## {label}")
        lines.append("")
        lines.append("| | n | Recall@1 | Recall@5 | MRR |")
        lines.append("|---|---|---|---|---|")
        for key, title in [("global", "Global"), ("fr", "Francais"), ("en", "Anglais")]:
            g = summ[key]
            if g:
                lines.append(f"| {title} | {g['n']} | {g['recall_at_1']} | {g['recall_at_5']} | {g['mrr']} |")
        lines.append(f"\nCas hors-catalogue (q25) traite honnetement (aucun resultat retourne) : {summ['out_of_catalog_handled_honestly']}")
        lines.append("")
    (OUT_DIR / "T5_rag_evaluation.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
