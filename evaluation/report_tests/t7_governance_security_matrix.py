"""T7 — Matrice gouvernance & securite : attendu vs obtenu, sans LLM.

Appelle directement les fonctions de production (toutes pures, sans DB/reseau
sauf mention contraire) avec des objets construits en memoire pour chaque cas.
Cas 10 (rate limit login) fait un vrai appel HTTP vers l'API live (localhost:8000).
Cas 5 (bulk sans approbation) et 11 (secret absent des args Celery) ne sont PAS
couverts ici — necessitent une orchestration live (DB+objets ORM reels pour 5,
pause du worker Celery pour 11) et sont traites separement.
"""
import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.approval.approval_guard import ApprovalRequiredError, assert_approval_for_real_execution
from app.automation.executor import PathTraversalError, _contains_traversal
from app.governance.policy_engine import ALLOW, BLOCK, REQUIRE_APPROVAL, check_execution_policy
from app.planner.models import AutomationPlan, BusinessIntent, PlanStep
from app.security.ssrf_guard import validate_target_url
from app.security.upload_limits import HAR_ALLOWED_SUFFIXES, validate_file_extension

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "evaluation" / "results" / "report"


class _Policy:
    def __init__(self, environment_policies, risk_threshold_low=1, risk_threshold_high=10):
        self.environment_policies = environment_policies
        self.risk_threshold_low = risk_threshold_low
        self.risk_threshold_high = risk_threshold_high


class _ForbiddenRule:
    def __init__(self, method, path_pattern):
        self.method = method
        self.path_pattern = path_pattern


def _plan(method: str, path: str = "/x", risk_level: str | None = None) -> AutomationPlan:
    rl = risk_level or {"GET": "low", "POST": "medium", "DELETE": "high"}.get(method.upper(), "low")
    step = PlanStep(
        order=1, endpoint_id="ep_test", canonical_key=f"{method} {path}", method=method, path=path,
        risk_level=rl,
    )
    return AutomationPlan(
        run_id="run_test", instruction="t7 test plan",
        intent=BusinessIntent(instruction="t7 test plan", intent="test", action="test"),
        workflow_name="t7_test_workflow", steps=[step],
    )


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


def run_cases() -> list[dict]:
    rows = []
    full_access_policy = _Policy(environment_policies={"test": "full_access"})

    # 1. GET / POST / DELETE en env de test, seuils par defaut (low=1, high=10)
    # Note: avec les seuils par defaut (low=1, high=10), le score de risque
    # maximal atteignable (DELETE = "high" = 10) n'excede JAMAIS le seuil
    # haut (10) puisque _check_risk_threshold teste risk_score > high (strict).
    # Un BLOCK par le seul score de risque est donc inatteignable par defaut ;
    # seules une regle d'endpoint interdit ou une politique d'environnement
    # peuvent produire un BLOCK tant que risk_threshold_high reste a 10.
    for method, expected in [("GET", ALLOW), ("POST", REQUIRE_APPROVAL), ("DELETE", REQUIRE_APPROVAL)]:
        r = check_execution_policy(_plan(method), full_access_policy, [], "test")
        rows.append({"cas": f"1. {method} en environnement full_access, seuils par defaut",
                     "attendu": expected, "obtenu": r.decision, "ok": r.decision == expected})

    # 2. Endpoint interdit (meme si demande par un role ADMIN -- role n'est pas
    #    un parametre de check_execution_policy : BLOCK ne depend jamais du role)
    forbidden = [_ForbiddenRule(method="DELETE", path_pattern="/employees/*")]
    r = check_execution_policy(_plan("DELETE", "/employees/42"), full_access_policy, forbidden, "test")
    rows.append({"cas": "2. Endpoint interdit par regle explicite (role ignore par construction)",
                 "attendu": BLOCK, "obtenu": r.decision, "ok": r.decision == BLOCK})

    # 3. Environnement sans politique configuree -> echec ferme (BLOCK)
    r = check_execution_policy(_plan("GET"), _Policy(environment_policies={}), [], "staging_sans_politique")
    rows.append({"cas": "3. Environnement sans politique configuree",
                 "attendu": BLOCK, "obtenu": r.decision, "ok": r.decision == BLOCK})

    # 4. OPERATOR lance une execution reelle sans approbation
    try:
        assert_approval_for_real_execution(dry_run=False, approval_granted=False)
        obtenu = "no_exception_raised"
    except ApprovalRequiredError:
        obtenu = "ApprovalRequiredError"
    rows.append({"cas": "4. Execution reelle (dry_run=False) sans approbation accordee",
                 "attendu": "ApprovalRequiredError", "obtenu": obtenu, "ok": obtenu == "ApprovalRequiredError"})

    # 6. SSRF -- 3 cibles interdites + 1 cible autorisee pour contraste
    ssrf_targets = [
        ("http://127.0.0.1/", "blocked"),
        ("http://10.0.0.5/", "blocked"),
        ("http://169.254.169.254/latest/meta-data/", "blocked"),
        ("https://example.com/", "allowed"),
    ]
    for url, expected in ssrf_targets:
        try:
            validate_target_url(url)
            obtenu = "allowed"
        except Exception:
            obtenu = "blocked"
        rows.append({"cas": f"6. SSRF -- cible {url}",
                     "attendu": expected, "obtenu": obtenu, "ok": obtenu == expected})

    # 7. Parametre de chemin ../../etc
    try:
        if _contains_traversal("../../etc"):
            raise PathTraversalError("detected")
        obtenu = "no_exception_raised"
    except PathTraversalError:
        obtenu = "PathTraversalError"
    rows.append({"cas": "7. Parametre de chemin '../../etc'",
                 "attendu": "PathTraversalError", "obtenu": obtenu, "ok": obtenu == "PathTraversalError"})

    # 8. Import d'un .txt a la place d'un .har
    try:
        validate_file_extension("capture.txt", HAR_ALLOWED_SUFFIXES)
        obtenu = "accepted"
    except Exception:
        obtenu = "HTTPException_400"
    rows.append({"cas": "8. Upload capture.txt comme fichier HAR",
                 "attendu": "HTTPException_400", "obtenu": obtenu, "ok": obtenu == "HTTPException_400"})

    # 9. CSV > 20 Mo et > 10000 lignes -- verification des constantes de config
    #    (la generation + l'appel reel au endpoint bulk est traitee separement dans T8;
    #    ici on verifie seulement que les limites configurees correspondent au brief)
    from app.core.config import settings
    rows.append({"cas": "9a. Limite de taille CSV configuree (BULK_FILE_MAX_SIZE_MB)",
                 "attendu": 20, "obtenu": settings.BULK_FILE_MAX_SIZE_MB,
                 "ok": settings.BULK_FILE_MAX_SIZE_MB == 20})
    rows.append({"cas": "9b. Limite de lignes CSV configuree (BULK_MAX_ROWS)",
                 "attendu": 10000, "obtenu": settings.BULK_MAX_ROWS,
                 "ok": settings.BULK_MAX_ROWS == 10000})

    # 10. 6 tentatives de login en moins d'une minute -- vrai appel HTTP (API live)
    try:
        codes = []
        for _ in range(6):
            resp = requests.post(
                "http://localhost:8000/auth/login",
                json={"email": "no-such-user@example.com", "password": "wrong"},
                timeout=5,
            )
            codes.append(resp.status_code)
        obtenu = "429_on_6th" if codes[5] == 429 else f"codes={codes}"
    except requests.exceptions.RequestException as exc:
        obtenu = f"api_unreachable ({exc.__class__.__name__})"
    rows.append({"cas": "10. 6 tentatives de login en moins d'une minute",
                 "attendu": "429_on_6th", "obtenu": obtenu, "ok": obtenu == "429_on_6th"})

    return rows


def main() -> None:
    rows = run_cases()
    meta = {
        "date_utc": datetime.now(timezone.utc).isoformat(),
        "commit": git_commit(),
        "commande": "python evaluation/report_tests/t7_governance_security_matrix.py",
        "note": "Cas 5 (bulk sans approbation) et 11 (secret absent des arguments Celery) "
                "non couverts ici -- necessitent une orchestration live separee.",
        "cases": rows,
        "reussis": sum(1 for r in rows if r["ok"]),
        "total": len(rows),
    }
    (OUT_DIR / "T7_gouvernance_securite.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(OUT_DIR / "T7_gouvernance_securite.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["cas", "attendu", "obtenu", "ok"])
        w.writeheader()
        w.writerows(rows)

    lines = ["# T7 — Matrice gouvernance & securite", "",
             f"- Date (UTC) : {meta['date_utc']} | Commit : `{meta['commit']}`",
             f"- {meta['reussis']}/{meta['total']} cas conformes (cas 5 et 11 non couverts ici)",
             "", "| Cas | Attendu | Obtenu | OK |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['cas']} | {r['attendu']} | {r['obtenu']} | {'o' if r['ok'] else 'n'} |")
    (OUT_DIR / "T7_gouvernance_securite.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
