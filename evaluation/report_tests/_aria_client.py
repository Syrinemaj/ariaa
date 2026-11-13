"""Petit client HTTP pour l'API ARIA live (localhost:8000), utilise par T5/T6/T8/T10.
Lit les identifiants depuis les variables d'environnement (jamais ecrits sur disque) :
ARIA_ADMIN_EMAIL / ARIA_ADMIN_PASSWORD / ARIA_OPERATOR_EMAIL / ARIA_OPERATOR_PASSWORD.
"""
import os
import time
import requests

BASE = "http://localhost:8000"


def login(email_env: str, password_env: str) -> str:
    email = os.environ[email_env]
    password = os.environ[password_env]
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"] if "access_token" in r.json() else r.json()["token"]


def admin_token() -> str:
    return login("ARIA_ADMIN_EMAIL", "ARIA_ADMIN_PASSWORD")


def operator_token() -> str:
    return login("ARIA_OPERATOR_EMAIL", "ARIA_OPERATOR_PASSWORD")


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def wait_job(job_id: str, token: str, timeout_s: int = 600, poll_s: int = 3) -> dict:
    start = time.time()
    while time.time() - start < timeout_s:
        r = requests.get(f"{BASE}/jobs/{job_id}", headers=headers(token), timeout=10)
        r.raise_for_status()
        data = r.json()
        if data["status"] in ("completed", "done", "failed", "partial"):
            return data
        time.sleep(poll_s)
    raise TimeoutError(f"job {job_id} did not complete within {timeout_s}s")
