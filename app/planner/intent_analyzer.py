from app.ai.azure_openai_client import AzureOpenAIClient
from app.ai.structured_outputs import BUSINESS_INTENT_SCHEMA
from app.planner.models import BusinessIntent


SYSTEM_PROMPT = """
You are a business automation intent analyzer.

Your task:
- understand the user's business instruction
- extract the business intent
- extract the business domain
- extract quantity if present
- extract entities involved
- decide if this is bulk execution
- return strict JSON only

Do not invent API endpoints.
"""


def analyze_business_intent(instruction: str) -> BusinessIntent:
    client = AzureOpenAIClient()
    result = client.structured_chat(
        system_prompt=SYSTEM_PROMPT,
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
