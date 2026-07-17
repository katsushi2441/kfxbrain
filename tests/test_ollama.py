import pytest

from kfxbrain.ollama import BrainError, extract_json_object, validate_result


def test_extract_json_object():
    assert extract_json_object('```json\n{"action":"hold"}\n```') == {"action": "hold"}


def test_extract_json_object_removes_empty_keys():
    assert extract_json_object('{"":"noise","ranking":[{"":"noise","pair":"EUR_USD"}]}') == {
        "ranking": [{"pair": "EUR_USD"}]
    }


def test_invalid_json_raises():
    with pytest.raises(BrainError):
        extract_json_object("not json")


def test_missing_required_result_fields_raise():
    with pytest.raises(BrainError, match="missing required fields"):
        validate_result("technical", {"signal": "neutral"})


def test_market_result_contract_is_validated():
    with pytest.raises(BrainError, match="missing required fields"):
        validate_result("market_opportunity_ranking", {})
