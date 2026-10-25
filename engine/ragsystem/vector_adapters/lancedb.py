import json
from pathlib import Path

from ragsystem.domain.errors import EngineError
from ragsystem.vector_adapters.base import ExactAdapter


class LanceDB(ExactAdapter):
    def __init__(self, path: Path, space_id: str, dimension: int, metric="cosine"):
        super().__init__(space_id, dimension, metric)
        import lancedb
        import pyarrow as pa

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = lancedb.connect(str(self.path))  # Local directory; never Cloud.
        schema = pa.schema(
            [
                pa.field("embedding_id", pa.string()),
                pa.field("vector", pa.list_(pa.float32(), dimension)),
            ],
            metadata={b"ragsystem_config": json.dumps([space_id, dimension, metric]).encode()},
        )
        self.schema = schema
        name = "space_" + space_id
        existing_names = self.db.list_tables().tables
        if name in existing_names:
            self.table = self.db.open_table(name)
            if (
                self.table.schema != schema
                or (self.table.schema.metadata or {}).get(b"ragsystem_config")
                != schema.metadata[b"ragsystem_config"]
            ):
                raise EngineError("SPACE_MISMATCH")
        else:
            self.table = self.db.create_table(name, schema=schema)

    def upsert(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        rows = [{"embedding_id": i, "vector": self.vector(v)} for i, v in entries]
        if rows:
            self.table.merge_insert(
                "embedding_id"
            ).when_matched_update_all().when_not_matched_insert_all().execute(rows)

    def delete(self, ids):
        self.validate_ids(ids)
        if ids:
            self.table.delete("embedding_id IN (" + ",".join("'" + i + "'" for i in ids) + ")")

    def ids(self):
        return set(self.table.to_arrow()["embedding_id"].to_pylist())

    def search_exact(self, query, eligible_embedding_ids, k):
        eligible = sorted(set(eligible_embedding_ids))
        vector = self.validate_query(query, eligible, k)
        if not eligible:
            return []
        predicate = "embedding_id IN (" + ",".join("'" + i + "'" for i in eligible) + ")"
        # Fetch the eligible distances to make exact ties deterministic across
        # backends. Measure this adapter overhead separately, not just the kernel.
        rows = (
            self.table.search(vector)
            .distance_type(self.metric)
            .bypass_vector_index()
            .where(predicate, prefilter=True)
            .limit(len(eligible))
            .to_list()
        )
        if self.metric == "l2":
            # Lance returns squared L2, sqlite-vec returns Euclidean L2.
            rows = [{**row, "_distance": max(0.0, float(row["_distance"])) ** 0.5} for row in rows]
        rows.sort(key=lambda row: (row["_distance"], row["embedding_id"]))
        return [
            {"embedding_id": row["embedding_id"], "distance": float(row["_distance"])}
            for row in rows[:k]
        ]

    def rebuild(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        rows = [{"embedding_id": i, "vector": self.vector(v)} for i, v in entries]
        self.table = self.db.create_table(
            "space_" + self.space_id, data=rows, schema=self.schema, mode="overwrite"
        )
        return self.check_integrity([i for i, _ in entries])
