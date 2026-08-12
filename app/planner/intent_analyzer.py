from typing import List, Optional

from app.ai.structured_outputs import BUSINESS_INTENT_SCHEMA
from app.planner.models import BusinessIntent


def _domain_instructions(known_domains: Optional[List[str]]) -> str:
    """
    Aria ingests traffic from arbitrary REST APIs, not just HR/payroll systems.
    A fixed domain enum overfits to one demo scenario and hurts RAG matching
    (business_domain feeds directly into the vector search query). Ground the
    model in whatever domains this run's endpoints were actually classified
    into, instead of a hardcoded list.
    """
    if known_domains:
        domain_list = ", ".join(known_domains)
        return (
            f"This analysis run's endpoints have been classified into these "
            f"business domains: {domain_list}.\n"
            f"Pick the closest matching domain from that list. If none fits "
            f"reasonably well, use a short lowercase word describing the "
            f"actual domain instead (do not force a bad fit)."
        )
    return (
        "No business domains are known yet for this run. Infer a short "
        "lowercase domain word yourself (e.g. \"hr\", \"payments\", "
        "\"inventory\", \"logistics\") from the instruction's content."
    )


SYSTEM_PROMPT_TEMPLATE = """
You are a business automation intent analyzer for REST API workflows.
You understand both French and English instructions.

Your task:
- Understand the user's business instruction
- Extract: intent (short english description), business domain, action type, entities, quantity
- Evaluate confidence (0.0 to 1.0): how clear and actionable is the instruction for API automation
- Decide if bulk execution is needed

DOMAIN GUIDANCE:
{domain_instructions}

CONFIDENCE SCALE:
  0.0–0.25 → Incomprehensible, off-topic, or clearly not a REST API action
  0.25–0.5 → Vague — might relate to business but not a concrete API action
  0.5–0.7  → Partial — describes an action but missing key entities or context
  0.7–1.0  → Clear — specific, actionable business API instruction with entities

BAD INSTRUCTIONS → set confidence < 0.25, reason="INSTRUCTION_UNCLEAR":
  ✗ "bonjour" — greeting, not an API action
  ✗ "test" — filler text
  ✗ "quelle heure est-il" — unrelated question
  ✗ "aaaaaaaaa" — keyboard mashing
  ✗ "fais quelque chose" — no concrete action or entity
  ✗ "améliore la base de données" — vague, no concrete REST API operation
  ✗ "je ne sais pas" — not an instruction

GOOD INSTRUCTIONS → set confidence >= 0.7, reason="OK" (domain examples below are
illustrative only — always prefer a domain from DOMAIN GUIDANCE above when one fits):
  ✓ "Créer un employé Bob Martin avec contrat CDI et envoyer un email de bienvenue"
     → action=create, domain=hr, entities=[employee,contract,email], confidence=0.92
  ✓ "Mettre à jour le salaire de l'employé ID 42 à 75000 EUR"
     → action=update, domain=payroll, entities=[employee,salary], confidence=0.88
  ✓ "Récupérer la liste des employés actifs du département Engineering"
     → action=fetch, domain=hr, entities=[employee,department], confidence=0.85
  ✓ "Ouvrir un compte paie et calculer les cotisations de janvier"
     → action=create, domain=payroll, entities=[account,salary,period], confidence=0.82
  ✓ "Créer un utilisateur avec rôle OPERATOR et envoyer ses identifiants par email"
     → action=create, domain=auth, entities=[user,role,email], confidence=0.90
  ✓ "Archiver les contrats expirés et notifier les managers concernés"
     → action=delete, domain=hr, entities=[contract,manager,notification], confidence=0.80
  ✓ "Supprimer un produit du catalogue"
     → action=delete, domain=products (or whatever this run's real domain is), entities=[product,catalog], confidence=0.85
  ✓ "Effectuer un paiement de 100 euros"
     → action=create, domain=payments, entities=[payment,amount], confidence=0.85

STRICT RULES:
1. If the instruction is unclear, nonsensical, or cannot map to a concrete REST API action,
   set confidence < 0.25 and reason="INSTRUCTION_UNCLEAR".
2. If instruction clearly describes a business API action with at least one entity,
   set confidence >= 0.7 and reason="OK".
3. NEVER invent or assume API endpoints — you analyze intent only.
4. Return ONLY valid JSON — no markdown fences, no text outside the JSON object.
5. reason must always be "OK" or "INSTRUCTION_UNCLEAR" from you. "NO_MATCHING_ENDPOINTS"
   is set by a LATER pipeline stage (after endpoint matching, which you don't perform) —
   never return it yourself, even if the instruction seems to require an endpoint
   that might not exist; that determination isn't yours to make here.

RESPONSE FORMAT (JSON only, no markdown):
{
  "intent": "short english description of the intent",
  "business_domain": "short lowercase domain word — see DOMAIN GUIDANCE above",
  "quantity": null or integer,
  "entities": ["entity1", "entity2"],
  "action": "create | update | delete | fetch | send | list | authenticate | other",
  "confidence": 0.0 to 1.0,
  "requires_bulk_execution": true or false,
  "reason": "OK" or "INSTRUCTION_UNCLEAR" or "NO_MATCHING_ENDPOINTS"
}
"""


def analyze_business_intent(
    instruction: str,
    client=None,
    known_domains: Optional[List[str]] = None,
) -> BusinessIntent:
    """
    Analyse an instruction and return a structured BusinessIntent.

    client — an AIClientProtocol instance (BedrockClient, GroqClient or
    AzureOpenAIClient). Falls back to create_ai_client() when not provided
    (Celery / standalone usage).
    known_domains — business domains already discovered for the target run
    (see planner/service.py::_get_known_domains). Grounds the domain guess in
    what actually exists instead of a fixed hr/payroll/auth/crm/other enum.
    """
    if client is None:
        from app.ai.base_client import create_ai_client
        client = create_ai_client()

    system_prompt = SYSTEM_PROMPT_TEMPLATE.replace(
        "{domain_instructions}", _domain_instructions(known_domains)
    )

    result = client.structured_chat(
        system_prompt=system_prompt,
        user_payload={"instruction": instruction},
        json_schema=BUSINESS_INTENT_SCHEMA,
        task_name="intent_analysis",
    )

    return BusinessIntent(
        instruction=instruction,
        intent=result["intent"],
        business_domain=result.get("business_domain"),
        quantity=result.get("quantity"),
        entities=result.get("entities", []),
        action=result["action"],
        confidence=float(result.get("confidence", 0.0)),
        requires_bulk_execution=bool(result.get("requires_bulk_execution", False)),
        reason=result.get("reason"),
    )
