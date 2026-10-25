import hashlib
import json
import math
import struct
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.storage.database import Database, utc_now


def encode_vector(vector, dimension):
    if len(vector) != dimension or not all(
        isinstance(x, (int, float)) and math.isfinite(x) for x in vector
    ):
        raise EngineError("VECTOR_INVALID")
    try:
        data = struct.pack("<" + "f" * dimension, *vector)
    except (OverflowError, struct.error) as exc:
        raise EngineError("VECTOR_INVALID") from exc
    if not all(math.isfinite(v) for v in struct.unpack("<" + "f" * dimension, data)):
        raise EngineError("VECTOR_INVALID")
    return data


class Embeddings:
    REQUIRED = {
        "model",
        "revision",
        "weight_sha256",
        "tokenizer_sha256",
        "preprocessing",
        "dimension",
        "metric",
        "normalization",
    }

    def __init__(self, db: Database):
        self.db = db

    def space(self, fingerprint):
        if (
            not self.REQUIRED <= set(fingerprint)
            or type(fingerprint["dimension"]) is not int
            or not 1 <= fingerprint["dimension"] <= 8192
        ):
            raise EngineError("SPACE_FINGERPRINT_INVALID")
        if fingerprint["metric"] not in {"cosine", "l2"} or fingerprint["normalization"] not in {
            "none",
            "l2",
        }:
            raise EngineError("SPACE_FINGERPRINT_INVALID")
        for field in ("weight_sha256", "tokenizer_sha256"):
            value = fingerprint[field]
            if (
                not isinstance(value, str)
                or len(value) != 64
                or any(c not in "0123456789abcdef" for c in value)
            ):
                raise EngineError("SPACE_FINGERPRINT_INVALID")
        try:
            text = json.dumps(
                fingerprint,
                sort_keys=True,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise EngineError("SPACE_FINGERPRINT_INVALID") from exc
        space_id = hashlib.sha256(text.encode()).hexdigest()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO embedding_spaces VALUES(?,?,?,?)",
                (space_id, text, fingerprint["dimension"], utc_now()),
            )
        return space_id

    def get(self, space_id, content_sha256):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM embedding_records WHERE space_id=? AND content_sha256=?",
                (space_id, content_sha256),
            ).fetchone()
            return dict(row) if row else None

    def persist(self, space_id, content_sha256, vector):
        if len(content_sha256) != 64 or any(c not in "0123456789abcdef" for c in content_sha256):
            raise EngineError("CONTENT_FINGERPRINT_INVALID")
        with self.db.transaction() as conn:
            space = conn.execute(
                "SELECT * FROM embedding_spaces WHERE id=?", (space_id,)
            ).fetchone()
            if space is None:
                raise EngineError("SPACE_UNKNOWN")
            data = encode_vector(vector, space["dimension"])
            config = json.loads(space["fingerprint_json"])
            decoded = struct.unpack("<" + "f" * space["dimension"], data)
            if config["metric"] == "cosine" and not any(decoded):
                raise EngineError("VECTOR_INVALID")
            if (
                config["normalization"] == "l2"
                and abs(sum(v * v for v in decoded) ** 0.5 - 1) > 1e-4
            ):
                raise EngineError("VECTOR_NORMALIZATION_INVALID")
            existing = conn.execute(
                "SELECT * FROM embedding_records WHERE space_id=? AND content_sha256=?",
                (space_id, content_sha256),
            ).fetchone()
            if existing:
                if existing["vector_bytes"] != data:
                    raise EngineError("EMBEDDING_CONFLICT", status=409)
                return existing["id"]
            record_id = str(uuid4())
            conn.execute(
                "INSERT INTO embedding_records VALUES(?,?,?,?,?)",
                (record_id, space_id, content_sha256, data, utc_now()),
            )
            return record_id

    def link(self, chunk_id, embedding_id):
        with self.db.transaction() as conn:
            row = conn.execute(
                """SELECT c.content_sha256 AS chunk_hash,e.content_sha256 AS vector_hash
                FROM chunks c JOIN embedding_records e ON e.id=? WHERE c.id=?""",
                (embedding_id, chunk_id),
            ).fetchone()
            if row is None or row["chunk_hash"] != row["vector_hash"]:
                raise EngineError("EMBEDDING_LINK_INVALID")
            conn.execute(
                "INSERT OR IGNORE INTO chunk_embedding_links VALUES(?,?)", (chunk_id, embedding_id)
            )

    def eligible(self, space_id, versions):
        if not 1 <= len(versions) <= 1000:
            raise EngineError("SCOPE_INVALID")
        with self.db.connection() as conn:
            return {
                row[0]
                for row in conn.execute(
                    f"""SELECT DISTINCT e.id FROM embedding_records e
                JOIN chunk_embedding_links l ON l.embedding_id=e.id JOIN chunks c ON c.id=l.chunk_id
                JOIN document_versions v ON v.id=c.doc_version_id WHERE e.space_id=? AND c.visible=1
                AND v.visibility='visible' AND v.id IN ({",".join("?" for _ in versions)})""",
                    [space_id, *versions],
                )
            }
