ENDPOINT_UNDERSTANDING_SCHEMA = {
    "name": "endpoint_understanding",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "business_domain": {"type": ["string", "null"]},
            "business_action": {"type": ["string", "null"]},
            "summary": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
        },
        "required": ["business_domain", "business_action", "summary", "description", "tags", "confidence"],
        "additionalProperties": False,
    },
}

WORKFLOW_UNDERSTANDING_SCHEMA = {
    "name": "workflow_understanding",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "name":            {"type": "string"},
            "business_domain": {"type": "string"},
            "summary":         {"type": "string"},
            "confidence":      {"type": "number"},
        },
        "required": ["name", "business_domain", "summary", "confidence"],
        "additionalProperties": False,
    },
}

BUSINESS_INTENT_SCHEMA = {
    "name": "business_intent",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "business_domain": {"type": ["string", "null"]},
            "quantity": {"type": ["integer", "null"]},
            "entities": {"type": "array", "items": {"type": "string"}},
            "action": {"type": "string"},
            "confidence": {"type": "number"},
            "requires_bulk_execution": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["intent", "business_domain", "quantity", "entities", "action", "confidence", "requires_bulk_execution", "reason"],
        "additionalProperties": False,
    },
}
