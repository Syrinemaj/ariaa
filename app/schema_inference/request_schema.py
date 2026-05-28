from typing import Any, Optional

from app.schema_inference.models import InferredSchema
from app.schema_inference.type_detector import infer_schema_from_value


def infer_request_schema(request_body: Optional[Any]) -> Optional[InferredSchema]:
    if request_body is None:
        return None

    schema = infer_schema_from_value(request_body)

    return InferredSchema(
        type=schema.get("type", "object"),
        properties=schema.get("properties", {}),
        required=schema.get("required", []),
    )
