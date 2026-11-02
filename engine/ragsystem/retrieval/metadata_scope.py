"""Intersect filters with an already authorized scope; separately detect changes."""

import json

from ragsystem.domain.errors import EngineError


def filter_metadata_scope(db, versions, filters):
    filters = filters or {}
    if not isinstance(filters, dict) or set(filters) - {"year_from", "year_to", "tag"}:
        raise EngineError("INVALID_FILTER")
    for key in ("year_from", "year_to"):
        if filters.get(key) is not None and (
            type(filters[key]) is not int or not 1000 <= filters[key] <= 2999
        ):
            raise EngineError("INVALID_FILTER")
    if filters.get("tag") is not None and (
        not isinstance(filters["tag"], str) or not 1 <= len(filters["tag"]) <= 200
    ):
        raise EngineError("INVALID_FILTER")
    if (
        filters.get("year_from") is not None
        and filters.get("year_to") is not None
        and filters["year_from"] > filters["year_to"]
    ):
        raise EngineError("INVALID_FILTER")
    if not any(value is not None for value in filters.values()):
        return list(versions), None
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT v.id,m.publication_year,m.tags_json,m.revision FROM document_versions v LEFT JOIN document_metadata m ON m.document_id=v.document_id WHERE v.id IN ("
            + ",".join("?" for _ in versions)
            + ") ORDER BY v.id",
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
    return [version for version in versions if version in matched], [tuple(row) for row in rows]


def require_metadata_snapshot(db, versions, filters, snapshot):
    if snapshot is not None and filter_metadata_scope(db, versions, filters)[1] != snapshot:
        raise EngineError("SCOPE_FILTER_CHANGED", status=409)
