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


def input_metadata(chunks, citations, excerpts):
    """Receipt authored by the trusted adapter from the final serialized input."""
    import hashlib
    import json

    inputs = {item["chunk_id"]: item for item in chunks}
    records = excerpt_audit(citations, excerpts)
    for record, excerpt in zip(records, excerpts, strict=True):
        chunk = inputs[record["chunk_id"]]
        record.update(
            start=0,
            end=len(excerpt["quote"]),
            text_sha256=hashlib.sha256(excerpt["quote"].encode()).hexdigest(),
            source_sha256=hashlib.sha256(
                json.dumps(chunk.get("source", {}), sort_keys=True).encode()
            ).hexdigest(),
        )
    included = [record["chunk_id"] for record in records]
    return {
        "contract_version": "model-input-v1",
        "included_chunk_ids": included,
        "dropped_chunk_ids": [
            item["chunk_id"] for item in chunks if item["chunk_id"] not in included
        ],
        "excerpt_lengths": records,
    }


def validate_input_metadata(metadata, chunks):
    """Reject missing/inconsistent receipts; never expand back to retrieval candidates."""
    import hashlib
    import json

    def invalid():
        raise EngineError("MODEL_INPUT_METADATA_INVALID")

    if not isinstance(metadata, dict) or metadata.get("contract_version") != "model-input-v1":
        invalid()
    pool = {item["chunk_id"]: item for item in chunks}
    included, dropped = metadata.get("included_chunk_ids"), metadata.get("dropped_chunk_ids")
    for ids in (included, dropped):
        if (
            not isinstance(ids, list)
            or any(not isinstance(key, str) or key not in pool for key in ids)
            or len(set(ids)) != len(ids)
        ):
            invalid()
    if set(included) & set(dropped) or set(included) | set(dropped) != set(pool):
        invalid()
    records = metadata.get("excerpt_lengths")
    if not isinstance(records, list) or len(records) != len(included):
        invalid()
    measured = {}
    for record, key in zip(records, included, strict=True):
        if not isinstance(record, dict) or record.get("chunk_id") != key:
            invalid()
        chunk, length = pool[key], record.get("included_characters")
        text = chunk["text"]
        if type(length) is not int or not 1 <= length <= min(1200, len(text)):
            invalid()
        if (
            type(record.get("original_characters")) is not int
            or record["original_characters"] != len(text)
            or type(record.get("start")) is not int
            or record["start"] != 0
            or type(record.get("end")) is not int
            or record["end"] != length
            or record.get("is_partial") is not (length < len(text))
        ):
            invalid()
        if (
            record.get("text_sha256") != hashlib.sha256(text[:length].encode()).hexdigest()
            or record.get("source_sha256")
            != hashlib.sha256(
                json.dumps(chunk.get("source", {}), sort_keys=True).encode()
            ).hexdigest()
        ):
            invalid()
        measured[key] = text[:length]
    return measured


MAX_CLAIMS = 2
MAX_CLAIM_CHARACTERS = 2000
MAX_CITATIONS = 5
MAX_COMPLETION_TOKENS = 900


def validate_answer(value, *, numbered=False):
    if not isinstance(value, dict) or set(value) - {"claims", "context_metadata"}:
        raise EngineError("MODEL_OUTPUT_INVALID")
    claims = value.get("claims")
    if not isinstance(claims, list) or len(claims) > MAX_CLAIMS:
        raise EngineError("MODEL_OUTPUT_INVALID")
    for claim in claims:
        if not isinstance(claim, dict) or set(claim) - {"text", "evidence", "conditions"}:
            raise EngineError("MODEL_OUTPUT_INVALID")
        if (
            not isinstance(claim.get("text"), str)
            or not 1 <= len(claim["text"].strip()) <= MAX_CLAIM_CHARACTERS
        ):
            raise EngineError("MODEL_OUTPUT_INVALID")
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not 1 <= len(evidence) <= MAX_CITATIONS:
            raise EngineError("MODEL_OUTPUT_INVALID")
        for item in evidence:
            fields = {"citation_id"} if numbered else {"chunk_id", "quote"}
            if (
                not isinstance(item, dict)
                or set(item) != fields
                or any(not isinstance(item[key], str) or not item[key] for key in fields)
            ):
                raise EngineError("MODEL_OUTPUT_INVALID")
        conditions = claim.get("conditions", {})
        if (
            not isinstance(conditions, dict)
            or len(conditions) > 10
            or any(
                not isinstance(key, str)
                or len(key) > 100
                or not isinstance(text, str)
                or len(text) > 1000
                for key, text in conditions.items()
            )
        ):
            raise EngineError("MODEL_OUTPUT_INVALID")
    return claims
