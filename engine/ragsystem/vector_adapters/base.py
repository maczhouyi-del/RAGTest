import re
import struct

from ragsystem.domain.errors import EngineError
from ragsystem.indexing.embeddings import encode_vector


class ExactAdapter:
    def __init__(self, space_id, dimension, metric="cosine"):
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", space_id)
            or not 1 <= dimension <= 8192
            or metric not in {"cosine", "l2"}
        ):
            raise EngineError("SPACE_INVALID")
        self.space_id, self.dimension, self.metric = space_id, dimension, metric

    @staticmethod
    def validate_ids(ids):
        if any(
            not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9:_-]{1,128}", i) for i in ids
        ):
            raise EngineError("VECTOR_ID_INVALID")

    def vector(self, values):
        encoded = encode_vector(values, self.dimension)
        result = list(struct.unpack("<" + "f" * self.dimension, encoded))
        if self.metric == "cosine" and not any(result):
            raise EngineError("VECTOR_INVALID")
        return result

    def validate_query(self, query, eligible, k):
        if not isinstance(k, int) or k <= 0:
            raise EngineError("K_INVALID")
        self.validate_ids(eligible)
        vector = self.vector(query)
        missing = set(eligible) - self.ids()
        if missing:
            raise EngineError("INDEX_INCOMPLETE", status=409)
        return vector

    def check_integrity(self, expected_ids):
        actual, expected = self.ids(), set(expected_ids)
        return {
            "ok": actual == expected,
            "missing": sorted(expected - actual),
            "unexpected": sorted(actual - expected),
        }

    def rebuild(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        for _, vector in entries:
            self.vector(vector)
        self.delete(sorted(self.ids()))
        self.upsert(entries)
        return self.check_integrity([entry[0] for entry in entries])
