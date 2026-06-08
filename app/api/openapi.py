from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin_or_operator
from app.db.session import get_db
from app.models.user import User
from app.openapi_builder.service import generate_openapi_for_run
from app.registry.repository import get_run_by_id

router = APIRouter(prefix="/openapi", tags=["OpenAPI"])


@router.get("/spec/{run_id}")
async def get_openapi_document(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin_or_operator),
):
    run = await get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    return await generate_openapi_for_run(db=db, run_id=run_id)
