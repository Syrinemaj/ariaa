from sqlalchemy.ext.asyncio import AsyncSession

from app.openapi_builder.builder import build_openapi_document
from app.registry.repository import get_endpoints_by_run_id


async def generate_openapi_for_run(db: AsyncSession, run_id: str) -> dict:
    endpoints = await get_endpoints_by_run_id(db=db, run_id=run_id)
    return build_openapi_document(
        title="ARIA Generated API",
        version="1.0.0",
        endpoints=endpoints,
    )
