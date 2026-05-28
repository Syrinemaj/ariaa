import pytest
from app.schema_inference.type_detector import detect_json_type, infer_schema_from_value


class TestDetectJsonType:
    def test_none(self):
        assert detect_json_type(None) == "null"

    def test_bool_true(self):
        assert detect_json_type(True) == "boolean"

    def test_bool_false(self):
        assert detect_json_type(False) == "boolean"

    def test_int(self):
        assert detect_json_type(42) == "integer"

    def test_float(self):
        assert detect_json_type(3.14) == "number"

    def test_string(self):
        assert detect_json_type("hello") == "string"

    def test_list(self):
        assert detect_json_type([1, 2, 3]) == "array"

    def test_dict(self):
        assert detect_json_type({"key": "val"}) == "object"


class TestInferSchemaFromValue:
    def test_primitive_string(self):
        assert infer_schema_from_value("hello") == {"type": "string"}

    def test_primitive_int(self):
        assert infer_schema_from_value(0) == {"type": "integer"}

    def test_primitive_bool(self):
        assert infer_schema_from_value(True) == {"type": "boolean"}

    def test_null(self):
        assert infer_schema_from_value(None) == {"type": "null"}

    def test_empty_array(self):
        result = infer_schema_from_value([])
        assert result == {"type": "array", "items": {}}

    def test_array_of_ints(self):
        result = infer_schema_from_value([1, 2, 3])
        assert result == {"type": "array", "items": {"type": "integer"}}

    def test_simple_object(self):
        result = infer_schema_from_value({"name": "Alice", "age": 30})
        assert result["type"] == "object"
        assert result["properties"]["name"] == {"type": "string"}
        assert result["properties"]["age"] == {"type": "integer"}
        assert "name" in result["required"]
        assert "age" in result["required"]

    def test_nested_object(self):
        result = infer_schema_from_value({"user": {"id": 1}})
        assert result["properties"]["user"]["type"] == "object"
        assert result["properties"]["user"]["properties"]["id"] == {"type": "integer"}

    def test_null_field_not_required(self):
        result = infer_schema_from_value({"active": None, "name": "Bob"})
        assert "active" not in result["required"]
        assert "name" in result["required"]
