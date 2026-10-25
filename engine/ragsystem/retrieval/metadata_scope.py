"""Validate an explicitly selected version scope against current manual metadata."""

import json

from ragsystem.domain.errors import EngineError


def require_metadata_scope(db, versions, filters):
    if not filters or not any(value is not None for value in filters.values()):
        return
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT v.id,m.publication_year,m.tags_json FROM document_versions v LEFT JOIN document_metadata m ON m.document_id=v.document_id WHERE v.id IN ("
            + ",".join("?" for _ in versions)
            + ")",
            versions,
        ).fetchall()
    matched = set()
    for row in rows:
        year = row["publication_year"]
        if filters.get("year_from") is not None and (year is None or year < filters["year_from"]):
            continue
        if filters.get("year_to") is not None and (year is None or year > filters["year_to"]):
            continue
        if filters.get("tag") is not None and filters["tag"] not in json.loads(
            row["tags_json"] or "[]"
        ):
            continue
        matched.add(row["id"])
    if matched != set(versions):
        raise EngineError("SCOPE_FILTER_CHANGED", status=409)
