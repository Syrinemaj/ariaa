"""
Mock API CRUD — simule un vrai système RH.
Lance avec :  python mock_api.py
Base URL :    http://localhost:9000

Stockage en mémoire (perdu au redémarrage).
Routes implémentées :
  POST   /api/v1/employees              → crée un employé, retourne {id, ...}
  GET    /api/v1/employees              → liste tous les employés
  GET    /api/v1/employees/{id}         → récupère un employé
  PATCH  /api/v1/employees/{id}         → met à jour un employé
  DELETE /api/v1/employees/{id}         → supprime un employé

  POST   /api/v1/contracts              → crée un contrat lié à un employé
  GET    /api/v1/contracts              → liste tous les contrats
  GET    /api/v1/contracts/{id}         → récupère un contrat

  PUT    /api/v1/employees/{id}/salary  → met à jour le salaire

  GET    /_mock/log                     → dernières 100 requêtes
  DELETE /_mock/log                     → vide le log
  GET    /_mock/db                      → état complet de la base en mémoire
  DELETE /_mock/db                      → remet la base à zéro
"""
import uuid
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="ARIA HR Mock API")

# ── Base de données en mémoire ────────────────────────────────────────────────
DB: dict = {
    "employees": {},   # id → employee dict
    "contracts": {},   # id → contract dict
}
REQUEST_LOG: list[dict] = []


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _log(method: str, path: str, body: dict, status: int, response: dict, headers: dict | None = None) -> None:
    REQUEST_LOG.append({
        "ts":       datetime.now().isoformat(timespec="milliseconds"),
        "method":   method,
        "path":     path,
        "headers":  headers or {},
        "body":     body,
        "status":   status,
        "response": response,
    })
    icon = "✓" if status < 400 else "✗"
    print(f"  {icon} {method} {path} → {status}")


# ── Employees ─────────────────────────────────────────────────────────────────

@app.post("/api/v1/employees", status_code=201)
async def create_employee(request: Request):
    body = await request.json()
    emp_id = _new_id("emp")
    employee = {
        "id":           emp_id,
        "firstName":    body.get("firstName", ""),
        "lastName":     body.get("lastName", ""),
        "email":        body.get("email", ""),
        "departmentId": body.get("departmentId", ""),
        "salary":       body.get("salary"),
        "contractType": body.get("contractType", ""),
        "startDate":    body.get("startDate", ""),
        "managerId":    body.get("managerId", ""),
        "createdAt":    datetime.now().isoformat(),
    }
    DB["employees"][emp_id] = employee
    _log("POST", "/api/v1/employees", body, 201, employee, headers=dict(request.headers))
    return JSONResponse(status_code=201, content=employee)


@app.get("/api/v1/employees")
async def list_employees():
    data = list(DB["employees"].values())
    _log("GET", "/api/v1/employees", {}, 200, {"count": len(data)})
    return {"employees": data, "total": len(data)}


@app.get("/api/v1/employees/{employee_id}")
async def get_employee(employee_id: str):
    emp = DB["employees"].get(employee_id)
    if not emp:
        _log("GET", f"/api/v1/employees/{employee_id}", {}, 404, {"error": "not found"})
        raise HTTPException(status_code=404, detail=f"Employee {employee_id!r} not found")
    _log("GET", f"/api/v1/employees/{employee_id}", {}, 200, emp)
    return emp


@app.patch("/api/v1/employees/{employee_id}")
async def update_employee(employee_id: str, request: Request):
    body = await request.json()
    emp = DB["employees"].get(employee_id)
    if not emp:
        _log("PATCH", f"/api/v1/employees/{employee_id}", body, 404, {"error": "not found"})
        raise HTTPException(status_code=404, detail=f"Employee {employee_id!r} not found")
    emp.update({k: v for k, v in body.items() if k != "id"})
    emp["updatedAt"] = datetime.now().isoformat()
    _log("PATCH", f"/api/v1/employees/{employee_id}", body, 200, emp)
    return emp


@app.delete("/api/v1/employees/{employee_id}", status_code=204)
async def delete_employee(employee_id: str):
    if employee_id not in DB["employees"]:
        raise HTTPException(status_code=404, detail=f"Employee {employee_id!r} not found")
    del DB["employees"][employee_id]
    _log("DELETE", f"/api/v1/employees/{employee_id}", {}, 204, {})
    return JSONResponse(status_code=204, content=None)


# ── Salary ────────────────────────────────────────────────────────────────────

@app.put("/api/v1/employees/{employee_id}/salary")
async def update_salary(employee_id: str, request: Request):
    body = await request.json()
    emp = DB["employees"].get(employee_id)
    if not emp:
        # Accept unknown IDs in bulk mode (salary update may reference a just-created employee)
        _log("PUT", f"/api/v1/employees/{employee_id}/salary", body, 200, {"updated": False, "reason": "employee not found, skipped"})
        return {"updated": False, "reason": "employee not found, skipped"}
    emp["salary"]    = body.get("amount", emp.get("salary"))
    emp["currency"]  = body.get("currency", "EUR")
    emp["updatedAt"] = datetime.now().isoformat()
    result = {"employeeId": employee_id, "newSalary": emp["salary"], "currency": emp["currency"]}
    _log("PUT", f"/api/v1/employees/{employee_id}/salary", body, 200, result)
    return result


# ── Contracts ─────────────────────────────────────────────────────────────────

@app.post("/api/v1/contracts", status_code=201)
async def create_contract(request: Request):
    body = await request.json()
    ctr_id = _new_id("ctr")
    contract = {
        "id":                  ctr_id,
        "employeeId":          body.get("employeeId", ""),
        "contractType":        body.get("contractType", ""),
        "startDate":           body.get("startDate", ""),
        "salary":              body.get("salary"),
        "currency":            body.get("currency", "EUR"),
        "workingHours":        body.get("workingHours"),
        "trialPeriodMonths":   body.get("trialPeriodMonths"),
        "createdAt":           datetime.now().isoformat(),
    }
    DB["contracts"][ctr_id] = contract
    _log("POST", "/api/v1/contracts", body, 201, contract)
    return JSONResponse(status_code=201, content=contract)


@app.get("/api/v1/contracts")
async def list_contracts():
    data = list(DB["contracts"].values())
    _log("GET", "/api/v1/contracts", {}, 200, {"count": len(data)})
    return {"contracts": data, "total": len(data)}


@app.get("/api/v1/contracts/{contract_id}")
async def get_contract(contract_id: str):
    ctr = DB["contracts"].get(contract_id)
    if not ctr:
        _log("GET", f"/api/v1/contracts/{contract_id}", {}, 404, {"error": "not found"})
        raise HTTPException(status_code=404, detail=f"Contract {contract_id!r} not found")
    _log("GET", f"/api/v1/contracts/{contract_id}", {}, 200, ctr)
    return ctr


# ── Inspection endpoints ──────────────────────────────────────────────────────

@app.get("/_mock/log")
def get_log():
    return {"total": len(REQUEST_LOG), "requests": REQUEST_LOG[-100:]}


@app.delete("/_mock/log")
def clear_log():
    REQUEST_LOG.clear()
    return {"cleared": True}


@app.get("/_mock/db")
def get_db():
    return {
        "employees": list(DB["employees"].values()),
        "contracts":  list(DB["contracts"].values()),
        "totals": {
            "employees": len(DB["employees"]),
            "contracts":  len(DB["contracts"]),
        },
    }


@app.delete("/_mock/db")
def reset_db():
    DB["employees"].clear()
    DB["contracts"].clear()
    REQUEST_LOG.clear()
    return {"reset": True}


# ── Catch-all pour les routes non implémentées ────────────────────────────────

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def catch_all(path: str, request: Request):
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    fake_id = _new_id("obj")
    response = {"id": fake_id, "status": "ok", "path": f"/{path}", "received": body}
    _log(request.method, f"/{path}", body, 200, response)
    return response


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("  ARIA HR Mock API  →  http://localhost:9000")
    print()
    print("  POST /api/v1/employees       → créer un employé")
    print("  GET  /api/v1/employees       → lister les employés")
    print("  POST /api/v1/contracts       → créer un contrat")
    print("  PUT  /api/v1/employees/{id}/salary  → maj salaire")
    print()
    print("  GET  /_mock/db               → voir tous les enregistrements")
    print("  GET  /_mock/log              → voir les requêtes reçues")
    print("  DELETE /_mock/db             → remettre à zéro")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=9000, log_level="warning")
