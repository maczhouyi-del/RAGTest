import importlib.util
import inspect
import json

import pytest
from ragsystem.domain.errors import EngineError
from ragsystem.models.local_generator import LocalGenerator

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("llama_cpp") is None,
    reason="Optional approved generation runtime not installed",
)


class ModelFixture:
    def __init__(self, output):
        self.output, self.kwargs = output, None

    def tokenize(self, value):
        return [0] * len(value.split())

    def create_chat_completion(self, **kwargs):
        from llama_cpp import Llama

        assert set(kwargs).issubset(inspect.signature(Llama.create_chat_completion).parameters)
        self.kwargs = kwargs
        marker = object()
        assert kwargs["logits_processor"]([1] * 32, marker) is marker
        return {"choices": [{"message": {"content": json.dumps(self.output)}}]}


def generator(output):
    result = object.__new__(LocalGenerator)
    result.model, result.cancel_check = ModelFixture(output), None
    return result


def test_numbered_quote_selection_is_exact_and_rejects_fabrication():
    value = generator({"claims": [{"text": "draft", "evidence": [{"citation_id": "E1"}]}]})
    result = value.generate(
        "answer",
        {"question": "?", "chunks": [{"chunk_id": "known-id", "text": "原文\nexact span"}]},
    )
    assert result["claims"][0]["evidence"] == [
        {"chunk_id": "known-id", "quote": "原文\nexact span"}
    ]
    assert "explicitly describe the conflict" in value.model.kwargs["messages"][0]["content"]
    with pytest.raises(EngineError, match="MODEL_OUTPUT_INVALID"):
        generator({"claims": [{"text": "draft", "evidence": [{"citation_id": "E999"}]}]}).generate(
            "answer", {"chunks": [{"chunk_id": "id", "text": "source"}]}
        )


def test_supported_runtime_callback_propagates_cancel():
    value = generator({"claims": []})

    def cancelled():
        raise EngineError("LEASE_LOST")

    value.cancel_check = cancelled
    with pytest.raises(EngineError, match="LEASE_LOST"):
        value.generate("answer", {"chunks": []})
