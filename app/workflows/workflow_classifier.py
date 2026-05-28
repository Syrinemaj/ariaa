from typing import List, Optional, Tuple

from app.workflows.models import WorkflowStep


HR_KEYWORDS = {"employee", "employees", "contract", "contracts", "onboarding", "department", "hire"}
FINANCE_KEYWORDS = {"invoice", "payment", "payments", "refund", "billing", "transaction"}
ECOMMERCE_KEYWORDS = {"cart", "checkout", "order", "orders", "product", "shipment"}


def _workflow_text(steps: List[WorkflowStep]) -> str:
    return " ".join(
        step.path.lower() + " " + str(step.action or "").lower()
        for step in steps
    )


def classify_workflow_name(steps: List[WorkflowStep]) -> Tuple[str, Optional[str], float]:
    text = _workflow_text(steps)

    hr_score = sum(1 for kw in HR_KEYWORDS if kw in text)
    finance_score = sum(1 for kw in FINANCE_KEYWORDS if kw in text)
    ecommerce_score = sum(1 for kw in ECOMMERCE_KEYWORDS if kw in text)

    scores = {
        "employee_onboarding": ("HR", hr_score),
        "finance_payment_flow": ("Finance", finance_score),
        "ecommerce_checkout": ("Ecommerce", ecommerce_score),
    }

    best_name = max(scores, key=lambda name: scores[name][1])
    best_domain, best_score = scores[best_name]

    if best_score == 0:
        return "generic_api_workflow", None, 0.40

    return best_name, best_domain, min(0.50 + best_score * 0.10, 0.95)
