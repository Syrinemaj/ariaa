"""T6 -- 8 scenarios de generation de plan, contre le vrai catalogue indexe
(run_id du gros HAR, 83 endpoints reels hr-rich-client/Sopra HR, anonymise).
Valeurs attendues definies AVANT execution (ci-dessous), comparees ensuite a
POST /automation/plan (chemin de production reel : intent_analyzer + RAG +
plan_generator). La decision de gouvernance est evaluee en appliquant
check_execution_policy (meme fonction pure que T7) au plan obtenu, avec une
politique de test "full_access" par defaut -- pas d'appel reel a /execute.
"""
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.governance.policy_engine import check_execution_policy

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "evaluation" / "results" / "report"
RUN_ID = "06f866a1-d8d6-4900-b3a0-cd3bc02c568c"
BASE = "http://localhost:8000"


class _Policy:
    environment_policies = {"test": "full_access"}
    risk_threshold_low = 1
    risk_threshold_high = 10


SCENARIOS = [
    {"id": "S1", "lang": "fr", "categorie": "creation simple",
     "instruction": "Creer un nouveau compteur de demandes de taches",
     "attendu": {"rejet_precoce": False, "action": "create", "endpoint_contains": "counters",
                 "bulk": False, "gouvernance": "REQUIRE_APPROVAL"}},
    {"id": "S2", "lang": "fr", "categorie": "lecture",
     "instruction": "Recuperer le plan du site",
     "attendu": {"rejet_precoce": False, "action": "fetch", "endpoint_contains": "sitemap",
                 "bulk": False, "gouvernance": "ALLOW"}},
    {"id": "S3", "lang": "fr", "categorie": "suppression (negatif -- pas de DELETE dans ce catalogue)",
     "instruction": "Supprimer le compte d'un utilisateur du systeme RH",
     "attendu": {"rejet_precoce": False, "action": "delete", "endpoint_contains": None,
                 "bulk": False, "gouvernance": None, "note": "aucun endpoint DELETE n'existe -- 0 etape attendue"}},
    {"id": "S4", "lang": "fr", "categorie": "dependance implicite",
     "instruction": "Connecter l'utilisateur puis recuperer les informations de l'utilisateur connecte",
     "attendu": {"rejet_precoce": False, "action": "multiple", "endpoint_contains": "login",
                 "bulk": False, "gouvernance": "REQUIRE_APPROVAL", "note": "2 etapes attendues avec dependance"}},
    {"id": "S5", "lang": "fr", "categorie": "masse (200 elements)",
     "instruction": "Mettre a jour le dossier RH de 200 employes",
     "attendu": {"rejet_precoce": False, "action": "update", "endpoint_contains": "dossier",
                 "bulk": True, "gouvernance": "REQUIRE_APPROVAL"}},
    {"id": "S6", "lang": "fr", "categorie": "instruction floue",
     "instruction": "Fais quelque chose avec le systeme",
     "attendu": {"rejet_precoce": True, "action": None, "endpoint_contains": None,
                 "bulk": None, "gouvernance": None}},
    {"id": "S7", "lang": "en", "categorie": "hors catalogue",
     "instruction": "Process a credit card refund for a customer order",
     "attendu": {"rejet_precoce": False, "action": "other", "endpoint_contains": None,
                 "bulk": False, "gouvernance": None, "note": "aucun endpoint pertinent attendu"}},
    {"id": "S8", "lang": "en", "categorie": "instruction en anglais",
     "instruction": "Check whether the current user session is still active",
     "attendu": {"rejet_precoce": False, "action": "fetch", "endpoint_contains": "pingsession",
                 "bulk": False, "gouvernance": "ALLOW"}},
]


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def eval_governance(plan_dict: dict) -> str | None:
    from app.planner.models import AutomationPlan
    if not plan_dict.get("steps"):
        return None
    plan = AutomationPlan.model_validate(plan_dict)
    r = check_execution_policy(plan, _Policy(), [], "test")
    return r.decision


def main() -> None:
    token = requests.post(f"{BASE}/auth/login", json={
        "email": os.environ["ARIA_ADMIN_EMAIL"], "password": os.environ["ARIA_ADMIN_PASSWORD"],
    }, timeout=10).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}

    rows = []
    for sc in SCENARIOS:
        r = requests.post(f"{BASE}/automation/plan", headers=h,
                           json={"run_id": RUN_ID, "instruction": sc["instruction"], "top_k": 8},
                           timeout=60)
        obtenu = {"status_code": r.status_code}
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:300]}

        if r.status_code == 200 and "plan" in body:
            plan = body["plan"]
            steps = plan.get("steps", [])
            gouvernance_obtenue = eval_governance(plan)
            obtenu.update({
                "rejet_precoce": False,
                "nb_etapes": len(steps),
                "endpoints": [s.get("path") for s in steps],
                "bulk": plan.get("intent", {}).get("requires_bulk_execution"),
                "confidence_intent": plan.get("intent", {}).get("confidence"),
                "gouvernance": gouvernance_obtenue,
            })
        else:
            obtenu.update({"rejet_precoce": True, "detail": body.get("detail", body)})

        ok_rejet = obtenu.get("rejet_precoce") == sc["attendu"]["rejet_precoce"]
        rows.append({"id": sc["id"], "categorie": sc["categorie"], "lang": sc["lang"],
                     "instruction": sc["instruction"], "attendu": sc["attendu"], "obtenu": obtenu,
                     "rejet_precoce_conforme": ok_rejet})
        print(f"{sc['id']} [{sc['categorie']}] -> rejet_precoce attendu={sc['attendu']['rejet_precoce']} "
              f"obtenu={obtenu.get('rejet_precoce')} | nb_etapes={obtenu.get('nb_etapes')} "
              f"| bulk={obtenu.get('bulk')} | gouvernance={obtenu.get('gouvernance')}")

    taux_reussite = sum(1 for r in rows if r["rejet_precoce_conforme"]) / len(rows)
    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(), "commit": git_commit(),
        "run_id": RUN_ID, "taux_reussite_rejet_precoce": round(taux_reussite, 3),
        "scenarios": rows,
    }
    (OUT_DIR / "T6_scenarios_plan.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = ["# T6 — 8 scenarios de generation de plan (catalogue reel)", "",
             f"- Date (UTC) : {meta['date_utc']} | Commit : `{meta['commit']}` | run_id : `{RUN_ID}`",
             f"- Conformite sur le critere 'rejet precoce attendu vs obtenu' : {taux_reussite*100:.0f}%", "",
             "| # | Categorie | Instruction | Nb etapes | Bulk | Gouvernance | Rejet precoce |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        o = r["obtenu"]
        lines.append(f"| {r['id']} | {r['categorie']} | {r['instruction']} | {o.get('nb_etapes','-')} | "
                      f"{o.get('bulk','-')} | {o.get('gouvernance','-')} | {o.get('rejet_precoce')} |")
    (OUT_DIR / "T6_scenarios_plan.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
