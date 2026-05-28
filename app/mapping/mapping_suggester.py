from typing import Any, Dict, List

from app.mapping.field_mapper import candidate_names, normalize_field_name


FIELD_SYNONYMS = {
    "firstName":    {"firstname", "first_name", "prenom", "prénom", "given_name"},
    "lastName":     {"lastname", "last_name", "nom", "surname", "family_name"},
    "email":        {"email", "mail", "email_address", "adresse_email"},
    "departmentId": {"department", "dept", "department_id", "departement", "departmentid"},
    "managerId":    {"manager", "manager_id", "managerid", "responsable"},
    "contractType": {"contract", "contract_type", "type_contrat", "contracttype"},
    "startDate":    {"start_date", "startdate", "date_debut", "hire_date", "joining_date"},
    "phone":        {"phone", "phone_number", "telephone", "mobile"},
}


def extract_target_fields_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    target_fields: List[Dict[str, Any]] = []

    for step in plan.get("steps", []):
        request_schema = step.get("request_schema") or {}
        properties = request_schema.get("properties", {})

        for field_name in properties.keys():
            target_fields.append({
                "target_field": field_name,
                "target_endpoint": step.get("canonical_key"),
                "step_order": step.get("order"),
            })

    return target_fields


def suggest_mappings(
    source_columns: List[str],
    plan: Dict[str, Any],
) -> List[Dict[str, Any]]:
    target_fields = extract_target_fields_from_plan(plan)
    suggestions: List[Dict[str, Any]] = []
    used_sources: set[str] = set()

    for target in target_fields:
        target_field = target["target_field"]
        target_norm = normalize_field_name(target_field)
        synonyms = FIELD_SYNONYMS.get(target_field, set())

        best_match = None
        best_confidence = 0.0
        best_source = "none"

        for source_column in source_columns:
            if source_column in used_sources:
                continue

            source_candidates = candidate_names(source_column)
            source_norm = normalize_field_name(source_column)

            if target_field in source_candidates:
                best_match, best_confidence, best_source = source_column, 1.0, "exact"
                break
            if target_norm in source_candidates:
                best_match, best_confidence, best_source = source_column, 0.95, "rules"
                break
            if source_norm in synonyms:
                best_match, best_confidence, best_source = source_column, 0.88, "synonym"
                break

        if best_match:
            used_sources.add(best_match)

        suggestions.append({
            "source_field": best_match,
            "target_field": target_field,
            "target_endpoint": target.get("target_endpoint"),
            "step_order": target.get("step_order"),
            "confidence": best_confidence,
            "source": best_source if best_match else "missing",
            "approved": best_confidence >= 0.90,
            "requires_reference_resolution": (
                target_field.lower().endswith("id")
                and best_match is not None
                and best_match.lower() not in {target_field.lower(), target_norm}
            ),
        })

    return suggestions
