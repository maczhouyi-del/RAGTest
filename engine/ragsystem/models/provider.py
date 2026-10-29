"""Generation contract; selecting a provider never changes the embedding space."""

from typing import Callable, Protocol

from ragsystem.domain.errors import EngineError

EVIDENCE_ANSWER_RULES = (
    "Assess all supplied current excerpts. If sources conflict, explicitly describe the conflict "
    "with citations to both sides; never silently select only a favorable result. "
    "Preserve experimental conditions, uncertainty and comparability limits. "
    "If the excerpts cannot answer the question, return empty claims. "
)


def numbered_excerpts(chunks):
    """One auditable formatter for local/network inputs; source IDs stay in Python."""
    if not isinstance(chunks, list) or len(chunks) > 100:
        raise EngineError("MODEL_INPUT_INVALID")
    citations, excerpts = {}, []
    for index, chunk in enumerate(chunks, 1):
        if (
            not isinstance(chunk, dict)
            or not isinstance(chunk.get("chunk_id"), str)
            or not isinstance(chunk.get("text"), str)
            or len(chunk["text"]) > 20000
        ):
            raise EngineError("MODEL_INPUT_INVALID")
        key, text = f"E{index}", chunk["text"]
        quote = text[:1200]
        citations[key] = {"chunk_id": chunk["chunk_id"], "quote": quote}
        excerpt = {
            "citation_id": key,
            "quote": quote,
            "original_characters": len(text),
            "included_characters": len(quote),
            "is_partial": len(quote) < len(text),
        }
        source = chunk.get("source")
        if source is not None:
            if not isinstance(source, dict):
                raise EngineError("MODEL_INPUT_INVALID")
            public = {}
            for name in ("document_label", "version_label", "title"):
                if name in source:
                    if not isinstance(source[name], str):
                        raise EngineError("MODEL_INPUT_INVALID")
                    public[name] = source[name][:300]
                    if name == "title" and len(source[name]) > 300:
                        public["title_is_partial"] = True
            if "page_number" in source:
                if type(source["page_number"]) is not int or source["page_number"] < 1:
                    raise EngineError("MODEL_INPUT_INVALID")
                public["page_number"] = source["page_number"]
            excerpt["source"] = public
        excerpts.append(excerpt)
    return citations, excerpts


def excerpt_audit(citations, excerpts):
    return [
        {
            "chunk_id": citations[item["citation_id"]]["chunk_id"],
            **{
                key: item[key]
                for key in ("original_characters", "included_characters", "is_partial")
            },
        }
        for item in excerpts
    ]


def model_usage(response):
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    measured = {
        key: usage[key]
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        if type(usage.get(key)) is int and usage[key] >= 0
    }
    return measured or None


class GenerationProvider(Protocol):
    fingerprint: dict
    cancel_check: Callable[[], None] | None

    def generate(self, task: str, data: dict) -> dict: ...
    def close(self) -> None: ...
