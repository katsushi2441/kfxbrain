import pytest

from kfxbrain.ollama import BrainError, extract_json_object, validate_result


def test_extract_json_object():
    assert extract_json_object('```json\n{"action":"hold"}\n```') == {"action": "hold"}


def test_invalid_json_raises():
    with pytest.raises(BrainError):
        extract_json_object("not json")


def test_missing_required_result_fields_raise():
    with pytest.raises(BrainError, match="missing required fields"):
        validate_result("technical", {"signal": "neutral"})
