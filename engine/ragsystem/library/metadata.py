"""Conservative local bibliographic candidates; never infer facts from file dates."""

import json
import re
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.jobs.repository import Jobs
from ragsystem.parsing.process import run_worker
from ragsystem.storage.database import utc_now

VERSION = "basic-bibliography-v1"
FIELDS = ("title", "authors", "year", "venue", "doi", "abstract")


def extract_candidates(attributes, pages):
    result = {}

    def add(field, value, method, page=None, excerpt=None):
        if value not in (None, "", []):
            from pydantic import ValidationError

            from ragsystem.library.repository import MetadataUpdate

            try:
                checked = MetadataUpdate.model_validate(
                    {"expected_revision": 0, "title": "candidate", field: value}
                )
            except ValidationError:
                return  # Invalid bibliographic fields stay explicitly unrecognized.
            value = checked.model_dump()[field]
            result[field] = {
                "value": value,
                "extraction_method": method,
                "source_page": page,
                "source_excerpt": (excerpt or "")[:8000] or None,
            }

    title = " ".join(attributes.get("Title", "").split())
    if 8 <= len(title) <= 1000 and not re.search(
        r"\.(?:pdf|docx?)$|^untitled$|^Microsoft Word", title, re.I
    ):
        add("title", title, "pdf_info:Title")
    author = attributes.get("Author", "").strip()
    # Only explicit separators, never guess how whitespace separates people.
    authors = [v.strip() for v in re.split(r"\s*;\s*|\r?\n|\s+and\s+|、", author) if v.strip()]
    if (
        authors
        and len(authors) <= 100
        and all(
            1 < len(v) <= 200
            and "@" not in v
            and not re.search(r"latex|microsoft|anonymous|unknown", v, re.I)
            for v in authors
        )
    ):
        add("authors", authors, "pdf_info:Author")
    first = pages[0]["text"] if pages else ""
    lines = [line.strip() for line in first.splitlines() if line.strip()]
    # Explicit publication header only; citations elsewhere are not publication dates.
    header = re.search(r"(?im)^(Proceedings of .{8,500})(?:\r?\n|$)", first[:1600])
    if header:
        venue = re.split(r",\s*pages?\s+\d", header[1], flags=re.I)[0].rstrip(",")
        add("venue", venue[:500], "first_page:proceedings", 1, header[0])
        years = set(re.findall(r"\b(?:19|20)\d{2}\b", header[1]))
        if len(years) == 1:
            add("year", int(next(iter(years))), "first_page:publication_header", 1, header[0])
    elif lines:
        journal = re.search(
            r"(?im)^(.{3,180}(?:Journal|Transactions|期刊|学报).{0,180})\b((?:19|20)\d{2})\b",
            first[:1200],
        )
        if journal:
            add("venue", journal[1].strip(), "first_page:journal", 1, journal[0])
            add("year", int(journal[2]), "first_page:journal", 1, journal[0])
    if "title" not in result:
        # A single explicit title line immediately before a clear Abstract heading
        # is not sufficient to infer arbitrary author/affiliation layouts.
        marked = re.search(r"(?im)^title\s*[:：]\s*(.{8,1000})$", first)
        if marked:
            add("title", marked[1].strip(), "first_page:labeled_title", 1, marked[0])
    dois = []
    for page in pages:
        for match in re.finditer(
            r'(?i)(?:https?://(?:dx\.)?doi\.org/|\bdoi\s*:\s*)(10\.\d{4,9}/[^\s<>"\x00-\x1f]+)',
            page["text"],
        ):
            value = match[1].rstrip(".,;")
            dois.append((value.lower(), page["page_number"], match[0]))
    if len({v[0] for v in dois}) == 1:
        value, page, excerpt = dois[0]
        add("doi", value, "first_pages:explicit_doi", page, excerpt)
    abstract = re.search(r"(?im)^(?:Abstract|摘\s*要)\s*[:：]?\s*\r?\n", first)
    if abstract:
        tail = first[abstract.end() :]
        boundary = re.search(
            r"(?im)^\s*(?:\d+(?:\.\d+)*\s+\S.{1,100}|(?:I\.?\s+)?INTRODUCTION|引言|Keywords\s*[:：]|关键词\s*[:：])\s*$",
            tail,
        )
        if boundary:
            text = tail[: boundary.start()].strip()
            if 80 <= len(text) <= 8000:
                add("abstract", text, "first_page:abstract_region", 1, text)
    return result


class MetadataExtraction:
    def __init__(self, db, root):
        self.db, self.root, self.jobs = db, root, Jobs(db)

    def ensure(self, version, connection=None):
        return self.jobs.enqueue(
            "verify",
            f"{VERSION}:{version}",
            {"action": "extract_metadata", "doc_version_id": version, "extractor_version": VERSION},
            connection=connection,
        )

    def ensure_missing(self):
        with self.db.connection() as conn:
            versions = [
                r[0]
                for r in conn.execute("SELECT id FROM document_versions WHERE visibility='visible'")
            ]
        for version in versions:
            self.ensure(version)

    def run_one(self, stopping=lambda: False):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT id FROM jobs WHERE type='verify' AND idempotency_key LIKE ? AND status IN ('queued','retry_wait') AND attempt_count<max_attempts ORDER BY created_at,id LIMIT 1",
                (VERSION + ":%",),
            ).fetchone()
        if not row:
            return False
        job = self.jobs.claim(row[0], lease_seconds=120)
        if not job:
            return False
        version = json.loads(job["payload_json"])["doc_version_id"]

        def check():
            if stopping():
                raise EngineError("METADATA_SHUTDOWN")
            with self.db.connection() as conn:
                self.jobs.require_lease(conn, job["id"], job["lease_token"])

        try:
            from ragsystem.library.repository import Library

            record = Library(self.db).file_record(version, self.root)
            result = run_worker(
                {
                    "operation": "metadata",
                    "pdf_path": str(self.root / "papers" / (record["file_sha256"] + ".pdf")),
                },
                timeout=30,
                check=check,
                log_directory=self.root / "metadata-worker-logs",
            )
            candidates = extract_candidates(result["attributes"], result["pages"])
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job["id"], job["lease_token"])
                document = conn.execute(
                    "SELECT document_id FROM document_versions WHERE id=?", (version,)
                ).fetchone()[0]
                for field, candidate in candidates.items():
                    conn.execute(
                        "INSERT OR IGNORE INTO metadata_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            str(uuid4()),
                            document,
                            version,
                            field,
                            json.dumps(candidate["value"], ensure_ascii=False),
                            candidate["extraction_method"],
                            candidate["source_page"],
                            candidate["source_excerpt"],
                            VERSION,
                            "unreviewed",
                            utc_now(),
                        ),
                    )
                self.jobs.complete(
                    job["id"], job["lease_token"], "metadata:" + version, connection=conn
                )
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "METADATA_EXTRACTION_FAILED"
            self.jobs.fail(job["id"], job["lease_token"], code)
            if code == "METADATA_SHUTDOWN":
                with self.db.transaction() as conn:
                    conn.execute(
                        "UPDATE jobs SET status='retry_wait' WHERE id=? AND status='failed' AND attempt_count<max_attempts",
                        (job["id"],),
                    )
        return True
