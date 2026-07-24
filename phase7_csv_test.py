import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.ai.groq_client import GroqClient
from app.rag.embeddings.client import LocalEmbeddingClient
from app.planner.service import create_plan_from_instruction


async def main():
    ai_client = GroqClient()
    embedding_client = LocalEmbeddingClient()

    async with AsyncSessionLocal() as db:
        plan, validation = await create_plan_from_instruction(
            db=db,
            run_id="75152650-6f9d-4adf-a841-b29a375b8b3b",
            instruction="Crée 3 employés",
            top_k=8,
            embedding_client=embedding_client,
            ai_client=ai_client,
            org_id="0d7f6484-7119-4e42-b6ec-4c88a1649e50",
            csv_columns=["prénom", "nom", "email", "type_contrat"],
        )

    print("=== VALIDATION ===")
    print(json.dumps(validation.model_dump(), indent=2, ensure_ascii=False))
    print("=== PLAN STEPS ===")
    for step in plan.steps:
        print(json.dumps({
            "canonical_key": step.canonical_key,
            "method": step.method,
            "path": step.path,
            "field_mapping": step.field_mapping,
        }, indent=2, ensure_ascii=False))
    print("=== METADATA (reasoning/confidence) ===")
    print(json.dumps({
        "reasoning": plan.metadata.get("reasoning"),
        "missing_endpoints": plan.metadata.get("missing_endpoints"),
        "plan_confidence": plan.metadata.get("plan_confidence"),
        "retrieved_endpoints": plan.metadata.get("retrieved_endpoints"),
    }, indent=2, ensure_ascii=False))


asyncio.run(main())
