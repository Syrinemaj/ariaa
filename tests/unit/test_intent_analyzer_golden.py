"""Golden-instruction regression tests for intent_analyzer.py's prompt.

These call the REAL LLM (AWS Bedrock — the only completion provider, no
mocking) — the whole point is to catch silent prompt regressions (e.g.
"bonjour" suddenly scoring confidence=0.6) that a mocked test can't detect,
since a mock just returns whatever we told it to. Skipped automatically when
AWS credentials aren't available (CI/local envs without them), and not meant
to gate every commit given the external dependency + per-call cost — run
manually or in a scheduled job.

analyze_business_intent(), called with no explicit client, resolves its
client via create_ai_client() — always a BedrockClient.
"""
import os

import pytest

from app.core.config import settings
from app.planner.intent_analyzer import analyze_business_intent


def _has_aws_credentials() -> bool:
    # boto3 resolves credentials from env vars / ~/.aws/credentials / IAM
    # role — env vars are the only form cheaply checkable without making a
    # real AWS call just to decide whether to skip.
    return bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_PROFILE"))


pytestmark = pytest.mark.skipif(
    not _has_aws_credentials(),
    reason="requires live AWS credentials — not mocked, hits a real Bedrock API",
)

# Mirrors the BAD/GOOD examples baked into intent_analyzer.SYSTEM_PROMPT_TEMPLATE.
# If the prompt changes and these start failing, that's the point.
BAD_INSTRUCTIONS = [
    "bonjour",
    "test",
    "quelle heure est-il",
    "aaaaaaaaa",
    "fais quelque chose",
    "améliore la base de données",
    "je ne sais pas",
]

GOOD_INSTRUCTIONS = [
    ("Créer un employé Bob Martin avec contrat CDI et envoyer un email de bienvenue", "create"),
    ("Mettre à jour le salaire de l'employé ID 42 à 75000 EUR", "update"),
    ("Récupérer la liste des employés actifs du département Engineering", "fetch"),
    ("Create a user with role OPERATOR and email their credentials", "create"),
    ("Delete the expired contracts and notify the managers", "delete"),
]


class TestBadInstructionsScoreLow:
    @pytest.mark.parametrize("instruction", BAD_INSTRUCTIONS)
    def test_confidence_below_plan_gate(self, instruction):
        intent = analyze_business_intent(instruction)
        assert intent.confidence < settings.PLAN_MIN_INTENT_CONFIDENCE, (
            f"{instruction!r} scored confidence={intent.confidence}, "
            f"expected < {settings.PLAN_MIN_INTENT_CONFIDENCE} (would wrongly "
            f"pass the /automation/plan confidence gate)"
        )


class TestGoodInstructionsScoreHigh:
    @pytest.mark.parametrize("instruction,expected_action", GOOD_INSTRUCTIONS)
    def test_confidence_above_plan_gate_and_action_correct(self, instruction, expected_action):
        intent = analyze_business_intent(instruction)
        assert intent.confidence >= 0.6, (
            f"{instruction!r} scored confidence={intent.confidence}, "
            f"expected >= 0.6 (would be wrongly rejected by the plan gate)"
        )
        assert intent.action == expected_action, (
            f"{instruction!r} → action={intent.action!r}, expected {expected_action!r}"
        )
        assert len(intent.entities) > 0, f"{instruction!r} extracted zero entities"


class TestKnownDomainsGrounding:
    def test_picks_known_domain_when_it_fits(self):
        intent = analyze_business_intent(
            "Effectuer un paiement de 100 euros",
            known_domains=["payments", "products", "hr"],
        )
        assert intent.business_domain == "payments"

    def test_does_not_force_bad_fit(self):
        # Only "hr" is known, but the instruction has nothing to do with HR —
        # the model should invent a sensible domain, not force "hr".
        intent = analyze_business_intent(
            "Supprimer un produit du catalogue e-commerce",
            known_domains=["hr"],
        )
        assert intent.business_domain != "hr"
