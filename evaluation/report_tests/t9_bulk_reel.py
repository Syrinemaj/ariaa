"""T9 -- Real bulk execution against absence-app, reached by NAME
(host.docker.internal) as ssrf_guard.py intends for dev targets.

Credentials come from env vars (never written to disk):
  ARIA_ADMIN_EMAIL / ARIA_ADMIN_PASSWORD   -- ARIA admin
  ABS_ADMIN_EMAIL  / ABS_ADMIN_PASSWORD    -- absence-app admin

Usage (state kept in evaluation/results/report/T9_state.json):
  python t9_bulk_reel.py setup                 # connection + CSV files
  python t9_bulk_reel.py run <label>           # upload -> ... -> real execution, waits for the job
  python t9_bulk_reel.py resume <label>        # re-enqueue unfinished batches of <label>
  python t9_bulk_reel.py counts                # rows in absence-app DB

Labels: nominal, idempotence, conflits, disjoncteur
"""
import csv
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OUT_DIR = ROOT / "evaluation" / "results" / "report"
STATE = OUT_DIR / "T9_state.json"
BASE = "http://localhost:8000"
ABS_LOCAL = "http://127.0.0.1:8010"
ABS_FROM_DOCKER = "http://host.docker.internal:8010"
ABS_DB = Path(r"C:\Users\MSI\absence-app\absences.db")
ANALYSIS_RUN_ID = "06f866a1-d8d6-4900-b3a0-cd3bc02c568c"  # org-scoping of data files only


def _schema(**fields):
    # Same shape as the request schema the HAR catalogue infers for an endpoint;
    # the payload mapper only sends fields declared here.
    return {"type": "object", "properties": {k: {"type": t} for k, t in fields.items()},
            "required": list(fields)}


SCHEMAS = {
    "/api/requests": _schema(employee_id="integer", type="string", date_debut="string",
                             date_fin="string", motif="string"),
    "/api/employees": _schema(full_name="string", email="string", department="string",
                              hire_date="string"),
}


def _plan(name, method, path, action, entity):
    return {
        "run_id": ANALYSIS_RUN_ID,
        "instruction": f"T9 {name}",
        "intent": {
            "instruction": f"T9 {name}", "intent": f"bulk_{action}_{entity}",
            "business_domain": "absence", "quantity": None, "entities": [entity],
            "action": action, "confidence": 0.95, "requires_bulk_execution": True, "reason": "OK",
        },
        "workflow_name": f"t9_{name}",
        "steps": [{
            "order": 1, "endpoint_id": f"manual_{entity}_{action}", "method": method,
            "path": path, "canonical_key": f"{method} {path}", "action": action,
            "business_domain": "absence", "depends_on": [], "risk_level": "medium",
            "field_mapping": {}, "request_schema": SCHEMAS[path],
        }],
    }


PLAN_REQUESTS = _plan("absence_requests", "POST", "/api/requests", "create", "absence_request")
PLAN_EMPLOYEES = _plan("employees", "POST", "/api/employees", "create", "employee")

RUNS = {
    "nominal": ("t8_bulk_100.csv", PLAN_REQUESTS),
    "idempotence": ("t8_bulk_100.csv", PLAN_REQUESTS),   # SAME file, uploaded again
    "conflits": ("t9_conflits_employes.csv", PLAN_EMPLOYEES),
    "disjoncteur": ("t9_disjoncteur_100.csv", PLAN_REQUESTS),
    # Re-run of the conflict experiment after two findings of the first one:
    # .test emails are rejected by the target (my data error), and duplicates
    # beyond the target's first list page were unresolved (fixed in
    # conflict_resolution.py). Different employees than the first file, since
    # those rows are now recorded as done by the idempotency store.
    "conflits2": ("t9_conflits2_employes.csv", PLAN_EMPLOYEES),
}


def setup_conflits2():
    state = load_state()
    c = sqlite3.connect(ABS_DB)
    c.row_factory = sqlite3.Row
    by_name = c.execute("SELECT id, full_name, email FROM employees ORDER BY full_name").fetchall()
    first_page, later = by_name[:20], by_name[20:]
    rows = [{"full_name": f"T9 Nouvel Employe {i}", "email": f"t9.nouveau{i}@example.com",
             "department": "QA", "hire_date": "2026-11-12"} for i in range(1, 6)]
    picks = {"dup_page1": first_page[8:11], "dup_page_suivante": later[60:63]}
    for chosen in picks.values():
        rows += [{"full_name": e["full_name"], "email": e["email"], "department": "QA",
                  "hire_date": "2026-11-12"} for e in chosen]
    state["conflits2_attendus"] = {k: [e["email"] for e in v] for k, v in picks.items()}
    with open(HERE / "t9_conflits2_employes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["full_name", "email", "department", "hire_date"])
        w.writeheader()
        w.writerows(rows)
    save_state(state)
    print("conflits2:", state["conflits2_attendus"])


def load_state():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def save_state(state):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def aria_headers():
    r = requests.post(f"{BASE}/auth/login", json={
        "email": os.environ["ARIA_ADMIN_EMAIL"], "password": os.environ["ARIA_ADMIN_PASSWORD"]}, timeout=10)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def counts():
    c = sqlite3.connect(ABS_DB)
    return {
        "absence_requests": c.execute("SELECT COUNT(*) FROM absence_requests").fetchone()[0],
        "employees": c.execute("SELECT COUNT(*) FROM employees").fetchone()[0],
    }


def setup():
    state = load_state()
    r = requests.post(f"{ABS_LOCAL}/api/auth/login", json={
        "email": os.environ["ABS_ADMIN_EMAIL"], "password": os.environ["ABS_ADMIN_PASSWORD"]}, timeout=10)
    r.raise_for_status()
    abs_token = r.json().get("access_token") or r.json().get("token")

    h = aria_headers()
    r = requests.post(f"{BASE}/connections", headers=h, json={
        "name": f"absence-app T9 {datetime.now():%H%M%S}", "base_url": ABS_FROM_DOCKER,
        "environment": "test", "auth_type": "service_account", "secret": abs_token}, timeout=10)
    print("create connection:", r.status_code, r.text[:200])
    r.raise_for_status()
    state["connection_id"] = r.json()["id"]

    c = sqlite3.connect(ABS_DB)
    c.row_factory = sqlite3.Row
    by_name = c.execute("SELECT id, full_name, email FROM employees ORDER BY full_name").fetchall()
    first_page, later = by_name[:20], by_name[20:]
    ids = [row["id"] for row in by_name]

    # Conflicts: 5 new employees, 3 duplicates visible on the target's first
    # list page (default page_size=20, ordered by full_name), 3 duplicates
    # beyond it.
    rows = [{"full_name": f"T9 Nouvel Employe {i}", "email": f"t9.nouveau{i}@absence-app.test",
             "department": "QA", "hire_date": "2026-11-12"} for i in range(1, 6)]
    picks = {"dup_page1": first_page[2:5], "dup_page_suivante": later[10:13]}
    for kind, chosen in picks.items():
        for e in chosen:
            rows.append({"full_name": e["full_name"], "email": e["email"], "department": "QA",
                         "hire_date": "2026-11-12"})
    state["conflits_attendus"] = {k: [e["email"] for e in v] for k, v in picks.items()}
    with open(HERE / "t9_conflits_employes.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["full_name", "email", "department", "hire_date"])
        w.writeheader()
        w.writerows(rows)

    types = ["conge", "maladie", "autre"]
    with open(HERE / "t9_disjoncteur_100.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "type", "date_debut", "date_fin", "motif"])
        for i in range(1, 101):
            month, day = (i % 12) + 1, (i % 27) + 1
            w.writerow([ids[i % len(ids)], types[i % 3], f"2028-{month:02d}-{day:02d}",
                        f"2028-{month:02d}-{day:02d}", f"Test T9 disjoncteur row {i}"])
    save_state(state)
    print("setup ok:", json.dumps({k: v for k, v in state.items() if k != "runs"}, ensure_ascii=False))


def _execute_with_approval(h, body):
    for _ in range(3):
        r = requests.post(f"{BASE}/bulk/execute", headers=h, json=body, timeout=120)
        if r.status_code in (200, 202):
            return r.json(), None
        detail = (r.json() or {}).get("detail") if r.content else None
        run_id = detail.get("automation_run_id") if isinstance(detail, dict) else None
        print("execute:", r.status_code, json.dumps(detail, ensure_ascii=False)[:300])
        if not run_id:
            return None, {"status": r.status_code, "detail": detail}
        a = requests.post(f"{BASE}/approvals/{run_id}/approve", headers=h,
                          json={"comment": "T9 approbation admin"}, timeout=30)
        print("approve:", a.status_code)
        body["existing_automation_run_id"] = run_id
    return None, {"status": "approval loop exhausted"}


def wait_job(h, job_id, timeout_s=300):
    start = time.time()
    while time.time() - start < timeout_s:
        p = requests.get(f"{BASE}/jobs/{job_id}/progress", headers=h, timeout=10).json()
        if p.get("status") in ("done", "partial", "failed", "completed"):
            return p, round(time.time() - start, 2)
        time.sleep(1)
    return p, None


def report(h, automation_run_id):
    r = requests.get(f"{BASE}/bulk/reports/{automation_run_id}", headers=h, timeout=30)
    return r.json() if r.ok else {"status": r.status_code, "text": r.text[:500]}


def run(label):
    state = load_state()
    csv_name, plan = RUNS[label]
    h = aria_headers()
    before = counts()

    with open(HERE / csv_name, "rb") as f:
        r = requests.post(f"{BASE}/bulk/data/upload", headers=h, params={"analysis_run_id": ANALYSIS_RUN_ID},
                          files={"file": (csv_name, f, "text/csv")}, timeout=30)
    r.raise_for_status()
    data_file_id = r.json()["data_file_id"]
    common = {"analysis_run_id": ANALYSIS_RUN_ID, "data_file_id": data_file_id, "plan": plan}
    for step in ("mapping/suggest", "validate"):
        r = requests.post(f"{BASE}/bulk/{step}", headers=h, json=common, timeout=60)
        print(f"{step}:", r.status_code, r.text[:200])
        r.raise_for_status()
    validation = r.json()

    body = {"plan": plan, "data_file_id": data_file_id, "connection_id": state["connection_id"],
            "dry_run": False}
    t0 = time.time()
    started, error = _execute_with_approval(h, body)
    result = {"label": label, "csv": csv_name, "data_file_id": data_file_id, "counts_before": before,
              "validation": {k: validation.get(k) for k in ("total_rows", "valid_rows", "invalid_rows")},
              "started_at": datetime.now(timezone.utc).isoformat()}
    if error:
        result["error"] = error
    else:
        progress, waited = wait_job(h, started["job_id"])
        result.update({"job_id": started["job_id"], "automation_run_id": started["automation_run_id"],
                       "progress": progress, "duration_s": round(time.time() - t0, 2),
                       "report": report(h, started["automation_run_id"])})
    result["counts_after"] = counts()
    state.setdefault("runs", {})[label] = result
    save_state(state)
    print(json.dumps({k: result.get(k) for k in ("label", "progress", "duration_s", "counts_before",
                                                 "counts_after", "error")}, ensure_ascii=False, indent=1))


def resume(label):
    state = load_state()
    prev = state["runs"][label]
    _, plan = RUNS[label]
    h = aria_headers()
    before = counts()
    r = requests.post(f"{BASE}/bulk/resume", headers=h, json={
        "job_id": prev["job_id"], "automation_run_id": prev["automation_run_id"],
        "data_file_id": prev["data_file_id"], "plan": plan,
        "connection_id": state["connection_id"], "dry_run": False}, timeout=60)
    print("resume:", r.status_code, r.text[:400])
    r.raise_for_status()
    time.sleep(2)
    progress, waited = wait_job(h, prev["job_id"])
    prev["resume"] = {"response": r.json(), "progress": progress, "counts_before": before,
                      "counts_after": counts(), "report": report(h, prev["automation_run_id"])}
    save_state(state)
    print(json.dumps({k: prev["resume"][k] for k in ("progress", "counts_before", "counts_after")}, indent=1))


def rerun(label):
    """New real execution of the SAME data file (failed rows retried, rows
    already done skipped by idempotency)."""
    state = load_state()
    prev = state["runs"][label]
    _, plan = RUNS[label]
    h = aria_headers()
    before = counts()
    body = {"plan": plan, "data_file_id": prev["data_file_id"], "connection_id": state["connection_id"],
            "dry_run": False}
    t0 = time.time()
    started, error = _execute_with_approval(h, body)
    res = {"counts_before": before}
    if error:
        res["error"] = error
    else:
        progress, _ = wait_job(h, started["job_id"])
        res.update({"automation_run_id": started["automation_run_id"], "progress": progress,
                    "duration_s": round(time.time() - t0, 2), "report": report(h, started["automation_run_id"])})
    res["counts_after"] = counts()
    prev.setdefault("relances", []).append(res)
    save_state(state)
    print(json.dumps({k: res.get(k) for k in ("progress", "duration_s", "counts_before", "counts_after", "error")},
                     indent=1))


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"setup": lambda: setup(), "setup-conflits2": lambda: setup_conflits2(), "counts": lambda: print(counts()),
     "run": lambda: run(sys.argv[2]), "resume": lambda: resume(sys.argv[2]),
     "rerun": lambda: rerun(sys.argv[2])}[cmd]()
