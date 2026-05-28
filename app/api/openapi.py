from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.openapi_builder.service import generate_openapi_for_run
from app.registry.repository import get_run_by_id

router = APIRouter(prefix="/openapi", tags=["OpenAPI"])


@router.get("/{run_id}")
async def get_openapi_document(
    run_id: str,
    db: Session = Depends(get_db),
):
    run = get_run_by_id(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Analysis run not found")

    return generate_openapi_for_run(db=db, run_id=run_id)
