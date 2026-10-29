"""Model input formatting fixtures; not real model quality tests."""

import importlib.util
import json

import pytest
from ragsystem.models.network_provider import NetworkProvider
from ragsystem.models.provider import numbered_excerpts
from test_generation_boundary import generator


def chunks():
    return [
        {
            "chunk_id": "private-id",
            "text": "x" * 1300,
            "source": {
                "document_label": "P1",
                "version_label": "V1",
                "title": "Saved title",
                "page_number": 4,
                "private_path": "/never-send",
                "api_key": "never-send",
            },
        }
    ]


def test_numbered_excerpts_keep_source_groups_and_explicit_partial_metadata():
    citations, excerpts = numbered_excerpts(chunks())
    assert citations == {"E1": {"chunk_id": "private-id", "quote": "x" * 1200}}
    assert excerpts[0]["source"] == {
        "document_label": "P1",
        "version_label": "V1",
        "title": "Saved title",
        "page_number": 4,
    }
    assert excerpts[0]["original_characters"] == 1300
    assert excerpts[0]["included_characters"] == 1200 and excerpts[0]["is_partial"] is True
    assert "never-send" not in json.dumps(excerpts)


@pytest.mark.skipif(
    importlib.util.find_spec("llama_cpp") is None, reason="optional local runtime absent"
)
def test_network_and_local_inputs_share_exact_numbering_and_source_metadata(monkeypatch):
    local = generator({"claims": [{"text": "fixture", "evidence": [{"citation_id": "E1"}]}]})
    actual = local.generate("answer", {"question": "fixture?", "chunks": chunks()})
    network = NetworkProvider(
        {
            "kind": "api",
            "id": "fixture",
            "name": "fixture",
            "base_url": "http://127.0.0.1:1/v1",
            "model": "fixture",
            "revision": 1,
        },
        "fixture-key",
    )
    bodies = []

    def request(path, body):
        bodies.append(body)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {"claims": [{"text": "fixture", "evidence": [{"citation_id": "E1"}]}]}
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        }

    monkeypatch.setattr(network, "request", request)
    remote = network.generate("answer", {"question": "fixture?", "chunks": chunks()})
    sent = json.loads(bodies[0]["messages"][1]["content"])
    local_sent = json.loads(local.model.kwargs["messages"][1]["content"])
    assert sent["excerpts"] == local_sent["excerpts"]
    assert remote["claims"] == actual["claims"]
    assert remote["context_metadata"]["usage"]["total_tokens"] == 30
    assert remote["context_metadata"]["excerpt_lengths"][0]["is_partial"] is True
