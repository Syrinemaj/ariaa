import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

DOWNLOADS = Path(r"C:\Users\MSI\Downloads")
BASE = "http://localhost:5173"
EMAIL = os.environ["ARIA_ADMIN_EMAIL"]
PASSWORD = os.environ["ARIA_ADMIN_PASSWORD"]
RUN_LABEL = "T10 - hr-rich-client (gros)"


def shot(page, name: str):
    path = DOWNLOADS / f"ARIA_{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print("saved:", path)


def select_run(page):
    page.locator("select").first.select_option(label=RUN_LABEL)
    page.wait_for_timeout(1500)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        page.goto(f"{BASE}/login", wait_until="networkidle")
        page.fill('input[type="email"]', EMAIL)
        page.fill('input[type="password"]', PASSWORD)
        page.click('button[type="submit"]')
        page.wait_for_timeout(2000)

        page.goto(f"{BASE}/endpoints", wait_until="networkidle")
        page.wait_for_timeout(1500)
        select_run(page)
        shot(page, "14_catalogue_endpoints_gros")

        page.goto(f"{BASE}/workflows", wait_until="networkidle")
        page.wait_for_timeout(1500)
        select_run(page)
        shot(page, "15_workflows_gros")

        page.goto(f"{BASE}/rag", wait_until="networkidle")
        page.wait_for_timeout(1500)
        try:
            select_run(page)
        except Exception as e:
            print("no run selector on /rag:", e)
        search_box = page.locator('input[type="text"], input[type="search"], input[placeholder]').first
        search_box.fill("Quel est le statut de report de conges d'un employe")
        page.keyboard.press("Enter")
        page.wait_for_timeout(4000)
        shot(page, "16_recherche_rag_resultat")

        page.goto(f"{BASE}/automation", wait_until="networkidle")
        page.wait_for_timeout(1500)
        try:
            select_run(page)
        except Exception as e:
            print("no run selector on /automation:", e)
        instr_box = page.locator("textarea").first
        instr_box.fill("Supprimer le compte d'un utilisateur du systeme RH")
        page.wait_for_timeout(300)
        submit_btn = page.get_by_role("button", name="Generate Plan")
        if submit_btn.count() == 0:
            submit_btn = page.get_by_role("button", name="Generate plan")
        if submit_btn.count() == 0:
            submit_btn = page.locator("button[type=submit]").first
        submit_btn.click()
        page.wait_for_timeout(5000)
        shot(page, "17_plan_suppression_substitution")

        browser.close()


if __name__ == "__main__":
    main()
