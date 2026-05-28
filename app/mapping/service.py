from sqlalchemy.orm import Session

from app.mapping.mapping_suggester import suggest_mappings
from app.mapping.mapping_validator import validate_mappings
from app.models.data_file import DataFile
from app.models.field_mapping import FieldMapping


def suggest_and_save_mappings(
    db: Session,
    analysis_run_id: str,
    data_file_id: str,
    plan: dict,
) -> dict:
    data_file = db.query(DataFile).filter(DataFile.id == data_file_id).first()

    if not data_file:
        raise ValueError("Data file not found")

    suggestions = suggest_mappings(source_columns=data_file.columns, plan=plan)

    for suggestion in suggestions:
        if not suggestion.get("source_field"):
            continue

        db.add(FieldMapping(
            analysis_run_id=analysis_run_id,
            source_field=suggestion["source_field"],
            target_field=suggestion["target_field"],
            target_endpoint_key=suggestion.get("target_endpoint"),
            confidence=suggestion.get("confidence", 0.0),
            source=suggestion.get("source", "rules"),
            approved=suggestion.get("approved", False),
        ))

    db.commit()

    validation = validate_mappings(mappings=suggestions, plan=plan)

    return {
        "data_file_id": data_file_id,
        "columns": data_file.columns,
        "mappings": suggestions,
        "validation": validation,
    }


def get_approved_mappings(db: Session, analysis_run_id: str) -> list[dict]:
    mappings = (
        db.query(FieldMapping)
        .filter(
            FieldMapping.analysis_run_id == analysis_run_id,
            FieldMapping.approved == True,  # noqa: E712
        )
        .all()
    )

    return [
        {
            "source_field": m.source_field,
            "target_field": m.target_field,
            "target_endpoint": m.target_endpoint_key,
            "confidence": m.confidence,
            "source": m.source,
            "approved": m.approved,
        }
        for m in mappings
    ]
