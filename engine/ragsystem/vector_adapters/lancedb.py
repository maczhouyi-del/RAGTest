import heapq
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
        return {
            value
            for batch in self.table.search().select(["embedding_id"]).limit(None).to_batches(256)
            for value in batch.column("embedding_id").to_pylist()
        }

    def search_exact(self, query, eligible_embedding_ids, k):
        eligible = sorted(set(eligible_embedding_ids))
        vector = self.validate_query(query, eligible, k)
        if not eligible:
            return []
        predicate = "embedding_id IN (" + ",".join("'" + i + "'" for i in eligible) + ")"
        # Exact ties require seeing every eligible distance. Stream only ID and
        # distance in bounded batches; retain O(k) Python rows, never all vectors.
        batches = (
            self.table.search(vector)
            .distance_type(self.metric)
            .bypass_vector_index()
            .where(predicate, prefilter=True)
            .select(["embedding_id", "_distance"])
            .limit(len(eligible))
            .to_batches(256)
        )
        def distances():
            for batch in batches:
                for row in batch.to_pylist():
                    distance = float(row["_distance"])
                    if self.metric == "l2":
                        distance = max(0.0, distance) ** 0.5
                    yield {"embedding_id": row["embedding_id"], "distance": distance}
        return heapq.nsmallest(k, distances(), key=lambda row: (row["distance"], row["embedding_id"]))

    def rebuild(self, entries):
        entries = list(entries)
        self.validate_ids([i for i, _ in entries])
        rows = [{"embedding_id": i, "vector": self.vector(v)} for i, v in entries]
        self.table = self.db.create_table(
            "space_" + self.space_id, data=rows, schema=self.schema, mode="overwrite"
        )
        return self.check_integrity([i for i, _ in entries])
