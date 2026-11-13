"""T8 -- Execution en masse contre absence-app (cible locale reelle).
Plan construit manuellement (pas issu du catalogue hr-rich-client) : une seule
etape POST /api/requests sur la connexion absence-app. Orchestration complete
du magicien /bulk (upload -> mapping -> approbation -> validation -> dry-run ->
execute -> approbation admin -> execution reelle).
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "evaluation" / "results" / "report"
BASE = "http://localhost:8000"
ANALYSIS_RUN_ID = "06f866a1-d8d6-4900-b3a0-cd3bc02c568c"  # pour l'org-scoping du data_file uniquement
CONNECTION_ID = "2449ed6e-3778-4ee7-9cad-e79d2a4f89d2"


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()


MANUAL_PLAN = {
    "run_id": ANALYSIS_RUN_ID,
    "instruction": "Creer des demandes d'absence en masse (T8)",
    "intent": {
        "instruction": "Creer des demandes d'absence en masse (T8)",
        "intent": "bulk_create_absence_request", "business_domain": "absence",
        "quantity": None, "entities": ["absence_request"], "action": "create",
        "confidence": 0.95, "requires_bulk_execution": True, "reason": "OK",
    },
    "workflow_name": "t8_bulk_absence_creation",
    "steps": [{
        "order": 1, "endpoint_id": "manual_absence_create", "method": "POST",
        "path": "/api/requests", "canonical_key": "POST /api/requests",
        "action": "create", "business_domain": "absence", "depends_on": [],
        "risk_level": "medium", "field_mapping": {},
    }],
}


def login(session: requests.Session) -> str:
    r = session.post(f"{BASE}/auth/login", json={
        "email": os.environ["ARIA_ADMIN_EMAIL"], "password": os.environ["ARIA_ADMIN_PASSWORD"],
    }, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def run_batch(csv_path: Path, label: str) -> dict:
    s = requests.Session()
    token = login(s)
    h = {"Authorization": f"Bearer {token}"}

    with open(csv_path, "rb") as f:
        r = s.post(f"{BASE}/bulk/data/upload", headers=h,
                    params={"analysis_run_id": ANALYSIS_RUN_ID},
                    files={"file": (csv_path.name, f, "text/csv")}, timeout=30)
    print(f"[{label}] upload:", r.status_code, r.text[:300])
    r.raise_for_status()
    data_file_id = r.json()["data_file_id"]

    r = s.post(f"{BASE}/bulk/mapping/suggest", headers=h,
               json={"analysis_run_id": ANALYSIS_RUN_ID, "data_file_id": data_file_id, "plan": MANUAL_PLAN},
               timeout=60)
    print(f"[{label}] mapping/suggest:", r.status_code, r.text[:500])
    r.raise_for_status()

    r = s.post(f"{BASE}/bulk/validate", headers=h,
               json={"analysis_run_id": ANALYSIS_RUN_ID, "data_file_id": data_file_id, "plan": MANUAL_PLAN},
               timeout=60)
    print(f"[{label}] validate:", r.status_code, r.text[:500])
    r.raise_for_status()
    validation = r.json()

    t0 = time.perf_counter()
    r = s.post(f"{BASE}/bulk/dry-run", headers=h,
               json={"analysis_run_id": ANALYSIS_RUN_ID, "data_file_id": data_file_id, "plan": MANUAL_PLAN,
                     "connection_id": CONNECTION_ID},
               timeout=60)
    t_dry_run = time.perf_counter() - t0
    print(f"[{label}] dry-run ({t_dry_run:.2f}s):", r.status_code, r.text[:500])

    t0 = time.perf_counter()
    r = s.post(f"{BASE}/bulk/execute", headers=h,
               json={"analysis_run_id": ANALYSIS_RUN_ID, "data_file_id": data_file_id, "plan": MANUAL_PLAN,
                     "connection_id": CONNECTION_ID, "dry_run": False},
               timeout=60)
    print(f"[{label}] execute (1st call):", r.status_code, r.text[:800])
    body = r.json() if r.content else {}

    return {
        "label": label, "data_file_id": data_file_id, "validation": validation,
        "dry_run_status": r.status_code, "t_dry_run_s": round(t_dry_run, 2),
        "execute_first_call": {"status": r.status_code, "body": body},
    }


if __name__ == "__main__":
    label = sys.argv[1] if len(sys.argv) > 1 else "100"
    csv_path = ROOT / "evaluation" / "report_tests" / f"t8_bulk_{label}.csv"
    result = run_batch(csv_path, label)
    out = OUT_DIR / f"T8_bulk_{label}_step1.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved:", out)
