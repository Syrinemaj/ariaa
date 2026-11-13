import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

DOWNLOADS = Path(r"C:\Users\MSI\Downloads")
DOWNLOADS.mkdir(parents=True, exist_ok=True)
BASE = "http://localhost:5173"
EMAIL = os.environ["ARIA_ADMIN_EMAIL"]
PASSWORD = os.environ["ARIA_ADMIN_PASSWORD"]


def shot(page, name: str):
    path = DOWNLOADS / f"ARIA_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("saved:", path)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(f"{BASE}/login", wait_until="networkidle")
        time.sleep(1)
        shot(page, "01_connexion")

        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_timeout(2500)
        shot(page, "02_apres_connexion")

        page.goto(f"{BASE}/dashboard", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "03_tableau_de_bord")

        page.goto(f"{BASE}/runs", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "04_historique_analyses")

        page.goto(f"{BASE}/endpoints", wait_until="networkidle")
        page.wait_for_timeout(2000)
        shot(page, "05_catalogue_endpoints")

        page.goto(f"{BASE}/workflows", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "06_workflows")

        page.goto(f"{BASE}/rag", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "07_recherche_rag_vide")

        page.goto(f"{BASE}/automation", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "08_automatisation")

        page.goto(f"{BASE}/bulk", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "09_execution_masse")

        page.goto(f"{BASE}/governance", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "10_gouvernance")

        page.goto(f"{BASE}/connections", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "11_connexions")

        page.goto(f"{BASE}/approvals", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "12_approbations")

        page.goto(f"{BASE}/audit-log", wait_until="networkidle")
        page.wait_for_timeout(1500)
        shot(page, "13_journal_audit")

        browser.close()


if __name__ == "__main__":
    main()
