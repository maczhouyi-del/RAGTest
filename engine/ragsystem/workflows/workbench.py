import hashlib
import json
import re
from contextlib import nullcontext
from uuid import uuid4

from ragsystem.domain.errors import EngineError
from ragsystem.jobs.repository import Jobs
from ragsystem.library.lifecycle import Lifecycle
from ragsystem.library.repository import Library
from ragsystem.models.generation_service import GenerationService
from ragsystem.parsing.tables import matching_cells
from ragsystem.retrieval.reranking import review_order
from ragsystem.retrieval.source_search import Sources
from ragsystem.retrieval.tokenizer import search_terms
from ragsystem.storage.database import utc_now
from ragsystem.verification.quotes import validate_quote
from ragsystem.workflows.system_information import question_parts, runtime_information


def identifier():
    return str(uuid4())


class Workbench:
    def __init__(self, db, root, search):
        self.db, self.root, self.search = db, root, search
        self.jobs, self.sources = Jobs(db), Sources(db, root)
        self.generation = GenerationService(db)

    def cancellation_check(self, job_id, token):
        with self.db.connection() as conn:
            self.jobs.require_lease(conn, job_id, token)

    def record_model(self, job_id, token, owner_id, generator, stage="generation"):
        # Commit before inference so failed/cancelled output still has provenance.
        fingerprint = json.loads(json.dumps(generator.fingerprint, sort_keys=True))
        with self.db.transaction() as conn:
            self.jobs.require_lease(conn, job_id, token)
            self.jobs.event(
                conn,
                job_id,
                "model_fingerprint",
                {
                    "owner_id": owner_id,
                    "stage": stage,
                    "fingerprint": fingerprint,
                },
            )
        return fingerprint

    @staticmethod
    def model_history(conn, owner_id):
        values = []
        for row in conn.execute(
            "SELECT e.job_id,e.details_json,e.created_at FROM events e JOIN jobs j ON j.id=e.job_id "
            "WHERE e.kind='model_fingerprint' AND j.type IN ('verify','research_extract') ORDER BY e.id"
        ):
            details = json.loads(row["details_json"])
            if details.get("owner_id") == owner_id:
                values.append(
                    {
                        "job_id": row["job_id"],
                        "created_at": row["created_at"],
                        "fingerprint": details["fingerprint"],
                        "stage": details.get("stage", "generation"),
                    }
                )
        return values

    @staticmethod
    def require_scope(conn, scope, versions=None):
        versions = versions or [value["doc_version_id"] for value in scope["versions"]]
        placeholders = ",".join("?" for _ in versions)
        suffix, params = "", []
        if scope["project_id"] is not None:
            suffix = " AND EXISTS(SELECT 1 FROM project_documents pd WHERE pd.document_id=v.document_id AND pd.project_id=? AND pd.linked=1)"
            params = [scope["project_id"]]
        eligible = {
            row[0]
            for row in conn.execute(
                f"SELECT v.id FROM document_versions v WHERE v.visibility='visible' AND v.id IN ({placeholders})"
                + suffix,
                [*versions, *params],
            )
        }
        if eligible != set(versions):
            raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
        original = {
            value["doc_version_id"]: value.get("document_id") for value in scope.get("versions", [])
        }
        for row in conn.execute(
            f"SELECT id,document_id FROM document_versions WHERE id IN ({placeholders})", versions
        ):
            if original.get(row[0]) is not None and original[row[0]] != row[1]:
                raise EngineError("SCOPE_IDENTITY_CHANGED", status=409)
        expected_runs = {
            value["doc_version_id"]: value["parse_run_ids"]
            for value in scope.get("versions", [])
            if value["doc_version_id"] in versions and "parse_run_ids" in value
        }
        if expected_runs:
            current = {version: [] for version in expected_runs}
            for row in conn.execute(
                f"SELECT DISTINCT p.doc_version_id,e.parse_run_id FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id IN ({placeholders}) ORDER BY e.parse_run_id",
                versions,
            ):
                if row[0] in current:
                    current[row[0]].append(row[1])
            if current != expected_runs:
                raise EngineError("SCOPE_STALE", status=409)

    def freeze(self, versions, project_id):
        if not versions or len(versions) > 1000:
            raise EngineError("SCOPE_NOT_AVAILABLE", status=409)
        versions = list(dict.fromkeys(versions))
        scope_id = identifier()
        with self.db.transaction() as conn:
            if project_id is not None:
                Library.require_project(conn, project_id)
            self.require_scope(conn, {"project_id": project_id}, versions)
            placeholders = ",".join("?" for _ in versions)
            eligible = {
                row["id"]: dict(row)
                for row in conn.execute(
                    f"SELECT v.id,v.document_id,v.file_sha256,v.parse_status,d.title FROM document_versions v JOIN documents d ON d.id=v.document_id WHERE v.id IN ({placeholders})",
                    versions,
                )
            }
            runs = {}
            for row in conn.execute(
                f"SELECT DISTINCT p.doc_version_id,e.parse_run_id FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id IN ({placeholders}) ORDER BY e.parse_run_id",
                versions,
            ):
                runs.setdefault(row[0], []).append(row[1])
            values = [
                {
                    "doc_version_id": version,
                    "document_id": eligible[version]["document_id"],
                    "file_sha256": eligible[version]["file_sha256"],
                    "title": eligible[version]["title"],
                    "parse_status": eligible[version]["parse_status"],
                    "parse_run_ids": runs.get(version, []),
                }
                for version in versions
            ]
            conn.execute(
                "INSERT INTO scope_snapshots VALUES(?,?,?,?)",
                (scope_id, project_id, json.dumps(values, ensure_ascii=False), utc_now()),
            )
        return scope_id

    def scope(self, scope_id):
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM scope_snapshots WHERE id=?", (scope_id,)).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        return dict(row) | {"versions": json.loads(row["versions_json"])}

    def create_conversation(self, project_id=None, title="新会话"):
        value, stamp = identifier(), utc_now()
        with self.db.transaction() as conn:
            if project_id is not None:
                Library.require_project(conn, project_id)
            conn.execute(
                "INSERT INTO conversations(id,title,project_id,created_at,updated_at) VALUES(?,?,?,?,?)",
                (value, title[:80], project_id, stamp, stamp),
            )
        return {"id": value, "title": title[:80], "created_at": stamp}

    def conversation_context(self, conn, conversation_id):
        # Strict character/UTF-8 bound (<= 6400 bytes), no new model calls.
        # Prior answers are non-evidence context, never added to the citation pool.
        rows = conn.execute(
            "SELECT id,COALESCE(json_extract(result_json,'$.literature_question'),question) AS question,status FROM answer_runs WHERE conversation_id=? AND status IN ('completed','refused') AND COALESCE(json_extract(result_json,'$.kind'),'') != 'system_info' ORDER BY created_at DESC,id DESC LIMIT 3",
            (conversation_id,),
        ).fetchall()
        result, remaining = [], 1600
        for row in rows:
            question = row["question"][: min(500, remaining)]
            remaining -= len(question)
            claims = conn.execute(
                "SELECT text FROM claim_records WHERE run_id=? AND model_support='supported' ORDER BY rowid LIMIT 2",
                (row["id"],),
            ).fetchall()
            answer = " ".join(r[0] for r in claims)[: min(300, remaining)]
            remaining -= len(answer)
            result.append(
                {
                    "question": question,
                    "answer_context_not_evidence": answer,
                    "status": row["status"],
                }
            )
            if remaining <= 0:
                break
        return list(reversed(result))

    @staticmethod
    def retrieval_context(question, context):
        reference = re.search(
            r"它们?|上述|前述|二者|两者|那这个|那(?:个|么|些)|这个呢|这些呢|继续(?:比较|对比|分析)"
            r"|\b(?:it|its|they|their|them|these|those|former|latter)\b",
            question,
            flags=re.I,
        )
        selected = context[-2:] if reference else []
        query = "\n".join([question, *(item["question"] for item in selected)])
        return selected, {
            "version": "current-question-first-v2",
            "strategy": "explicit_reference_last_two" if selected else "current_question_only",
            "turns": len(selected),
            "character_budget": 1600,
            "retrieval_query": query,
        }

    def create_answer(
        self,
        question,
        versions,
        project_id,
        mode,
        strategy,
        conversation_id=None,
        provider_id=None,
        allow_external=False,
        provider_revision=None,
        per_paper_limit=3,
    ):
        if (
            not question.strip()
            or type(per_paper_limit) is not int
            or not 1 <= per_paper_limit <= 8
            or mode not in {"extractive", "generative"}
            or strategy
            not in {
                "fts_only",
                "keyword",
                "vector_exact",
                "hybrid",
                "keyword_review",
                "hybrid_review",
            }
        ):
            raise EngineError("INVALID_REQUEST")
        if any(
            term in question.casefold()
            for term in (
                "所有论文",
                "全部论文",
                "整库",
                "全库",
                "all papers",
                "every paper",
                "systematic review",
            )
        ):
            raise EngineError("RESEARCH_REQUIRED", status=409)
        system_topics, literature_question = question_parts(question)
        system_topic = system_topics[0] if system_topics and not literature_question else None
        provider = None
        if not system_topic and mode == "generative" and provider_id not in {None, "local"}:
            provider = self.generation.providers.freeze(
                provider_id, allow_external, provider_revision
            )
        if system_topic:
            scope_id = identifier()
            with self.db.transaction() as conn:
                if project_id is not None:
                    Library.require_project(conn, project_id)
                conn.execute(
                    "INSERT INTO scope_snapshots VALUES(?,?,?,?)",
                    (scope_id, project_id, "[]", utc_now()),
                )
        else:
            scope_id = self.freeze(versions, project_id)
        run_id = identifier()
        with self.db.transaction() as conn:
            if conversation_id:
                row = conn.execute(
                    "SELECT * FROM conversations WHERE id=?", (conversation_id,)
                ).fetchone()
                if row is None or row["project_id"] != project_id:
                    raise EngineError("CONVERSATION_SCOPE_MISMATCH", status=409)
                if conn.execute(
                    "SELECT 1 FROM answer_runs a JOIN jobs j ON j.id=a.job_id WHERE a.conversation_id=? AND j.status IN ('queued','running')",
                    (conversation_id,),
                ).fetchone():
                    raise EngineError("CONVERSATION_BUSY", status=409)
            else:
                conversation_id = identifier()
                conn.execute(
                    "INSERT INTO conversations(id,title,project_id,created_at,updated_at) VALUES(?,?,?,?,?)",
                    (conversation_id, question[:80], project_id, utc_now(), utc_now()),
                )
            context = self.conversation_context(conn, conversation_id)
            conn.execute(
                "UPDATE conversations SET updated_at=?,title=CASE WHEN NOT EXISTS(SELECT 1 FROM answer_runs WHERE conversation_id=?) THEN ? ELSE title END WHERE id=?",
                (utc_now(), conversation_id, question[:80], conversation_id),
            )
            job = self.jobs.enqueue(
                "verify",
                run_id,
                {
                    "run_id": run_id,
                    "system_topic": system_topic,
                    "system_topics": system_topics,
                    "literature_question": literature_question,
                    "selected_generation_model": (
                        "extractive" if mode == "extractive" else provider_id or "local"
                    ),
                    "conversation_context": context,
                    "per_paper_limit": per_paper_limit,
                    **({"generation_provider": provider} if provider else {}),
                },
                connection=conn,
            )
            conn.execute(
                "INSERT INTO answer_runs VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    conversation_id,
                    scope_id,
                    question,
                    mode,
                    strategy,
                    job["id"],
                    "queued",
                    None,
                    None,
                    utc_now(),
                ),
            )
        return {
            "id": run_id,
            "conversation_id": conversation_id,
            "job_id": job["id"],
            "status": "queued",
        }

    def chunks_for(self, version):
        with self.db.connection() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """SELECT c.* FROM chunks c JOIN document_versions v ON v.id=c.doc_version_id
                WHERE c.doc_version_id=? AND c.visible=1 AND v.visibility='visible' ORDER BY c.page_number,c.start_offset,c.id""",
                    (version,),
                )
            ]

    def current_runs(self, version, connection=None):
        with self.db.connection() if connection is None else nullcontext(connection) as conn:
            return sorted(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT e.parse_run_id FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id=?",
                    (version,),
                )
            )

    def evidence(self, conn, owner, chunk_id, quote, pool):
        offsets = validate_quote(pool, chunk_id, quote)
        anchor = self.sources.anchor(chunk_id)
        start = anchor["clean_text_offsets"]["start"]
        table_candidates = matching_cells(
            conn, anchor["element_id"], start + offsets["start"], start + offsets["end"]
        )
        record = identifier()
        conn.execute(
            "INSERT INTO evidence_records(id,owner_id,source_anchor_id,quote,anchor_json,created_at) VALUES(?,?,?,?,?,?)",
            (
                record,
                owner,
                chunk_id,
                quote,
                json.dumps(
                    anchor
                    | {
                        "quote_offsets_in_chunk": offsets,
                        "quote_sha256": hashlib.sha256(quote.encode()).hexdigest(),
                        "table_candidates": table_candidates,
                    }
                ),
                utc_now(),
            ),
        )
        return record

    def run_answer(self, run_id):
        with self.db.connection() as conn:
            run = dict(conn.execute("SELECT * FROM answer_runs WHERE id=?", (run_id,)).fetchone())
        job = self.jobs.claim(run["job_id"], lease_seconds=1800)
        if job is None:
            return
        token = job["lease_token"]
        external_generators = []
        provider = None
        result = None
        stage = "retrieval"
        try:
            payload = json.loads(job["payload_json"])
            if payload.get("system_topic"):
                stage = "system_info"
                result = runtime_information(
                    self,
                    payload["system_topic"],
                    payload["selected_generation_model"],
                    run["strategy"],
                )
                if len(payload.get("system_topics", [])) > 1:
                    sections = [
                        runtime_information(
                            self, topic, payload["selected_generation_model"], run["strategy"]
                        )
                        for topic in payload["system_topics"]
                    ]
                    result["system_information"] = sections
                    result["text"] = "\n".join(section["text"] for section in sections)
                with self.db.transaction() as conn:
                    self.jobs.require_lease(conn, job["id"], token)
                    conn.execute(
                        "UPDATE answer_runs SET status='completed',result_json=?,error_code=NULL WHERE id=?",
                        (json.dumps(result, ensure_ascii=False), run_id),
                    )
                    self.jobs.complete(job["id"], token, "answer_run:" + run_id, connection=conn)
                return
            scope = self.scope(run["scope_id"])
            provider = json.loads(job["payload_json"]).get("generation_provider")

            def selected_generator():
                if provider:
                    from ragsystem.models.network_provider import definition

                    if definition(self.generation.providers.get(provider["id"])) != provider:
                        raise EngineError("PROVIDER_CHANGED", status=409)
                    selected = self.generation.require(provider["id"])
                    external_generators.append(selected)
                    return selected
                return self.generation.require()

            versions = [value["doc_version_id"] for value in scope["versions"]]
            for document in scope["versions"]:
                if self.current_runs(document["doc_version_id"]) != document["parse_run_ids"]:
                    raise EngineError("SCOPE_STALE")
            context = payload.get("conversation_context", [])
            question = payload.get("literature_question", run["question"])
            context, context_policy = self.retrieval_context(question, context)
            result = {
                "intent": "mixed" if payload.get("system_topics") else "literature",
                "literature_question": question,
                "context_policy": context_policy,
                "retrieval_status": "not_completed",
            }
            retrieval = self.search.search(
                context_policy["retrieval_query"],
                versions,
                8,
                scope["project_id"],
                run["strategy"].removesuffix("_review"),
                json.loads(job["payload_json"]).get("per_paper_limit", 3),
            )
            hits = retrieval["results"]
            result = {
                "kind": "evidence_only",
                "intent": "mixed" if payload.get("system_topics") else "literature",
                "literature_question": question,
                "system_information": [
                    runtime_information(
                        self, topic, payload["selected_generation_model"], run["strategy"]
                    )
                    for topic in payload.get("system_topics", [])
                ],
                "retrieval_status": "hits" if hits else "no_hits",
                "context_policy": context_policy,
                "retrieval": {key: value for key, value in retrieval.items() if key != "results"},
                "claims": [],
                "evidence_ids": [],
                "coverage": "Top-K local retrieval; not whole-library coverage",
            }
            result["retrieval"]["hits"] = [
                {key: value for key, value in hit.items() if key != "preview"} for hit in hits
            ]
            ranking = None
            if run["strategy"].endswith("_review") and hits:
                stage = "relevance_review"
                # This experiment is local-only, even when answer generation uses
                # an explicitly selected network provider. Never borrow its API.
                reviewer = self.generation.require()
                self.record_model(job["id"], token, run_id, reviewer, stage="relevance")
                reviewer.cancel_check = lambda: self.cancellation_check(job["id"], token)
                hits, ranking = review_order(reviewer, question, hits)
            pool = {hit["chunk_id"]: hit["preview"] for hit in hits}
            result["relevance_review"] = ranking
            raw_claims = []
            if run["mode"] == "generative" and hits:
                stage = "generation"
                generator = selected_generator()
                self.record_model(job["id"], token, run_id, generator)
                generator.cancel_check = lambda: self.jobs.heartbeat(job["id"], token, seconds=1800)
                raw = generator.generate(
                    "answer",
                    {
                        "question": question,
                        "conversation_context_not_evidence": context,
                        "chunks": [{"chunk_id": key, "text": value} for key, value in pool.items()],
                    },
                )
                raw_claims = raw.get("claims") if isinstance(raw, dict) else None
                if not isinstance(raw_claims, list) or len(raw_claims) > 6:
                    raise EngineError("MODEL_OUTPUT_INVALID")
                result["kind"] = "generated_draft"
                result["model_fingerprint"] = generator.fingerprint
                result["model_context"] = raw.get("context_metadata")
            checked = []
            stage = "citation_validation"
            for claim in raw_claims:
                stage = "citation_validation"
                if (
                    not isinstance(claim, dict)
                    or not isinstance(claim.get("text"), str)
                    or not 1 <= len(claim["text"]) <= 2000
                    or not isinstance(claim.get("evidence"), list)
                    or not 1 <= len(claim["evidence"]) <= 5
                ):
                    raise EngineError("MODEL_OUTPUT_INVALID")
                for item in claim["evidence"]:
                    if not isinstance(item, dict):
                        raise EngineError("MODEL_OUTPUT_INVALID")
                    validate_quote(pool, item.get("chunk_id"), item.get("quote"))
                self.jobs.heartbeat(job["id"], token, seconds=1800)
                stage = "support_check"
                support = generator.generate(
                    "support",
                    {
                        "question": question,
                        "claim": claim["text"],
                        "evidence": claim["evidence"],
                    },
                )
                if (
                    not isinstance(support, dict)
                    or support.get("status") not in {"supported", "contradicted", "uncertain"}
                    or not isinstance(support.get("reason"), str)
                    or len(support["reason"]) > 2000
                ):
                    raise EngineError("MODEL_OUTPUT_INVALID")
                checked.append((claim, support))
            if provider and run["mode"] == "generative" and hits:
                self.generation.providers.mark_generation(provider["id"])
            result["support_checks"] = []
            result["claim_details"] = []
            stage = "publication"
            self.jobs.heartbeat(job["id"], token, seconds=1800)
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job["id"], token)
                self.require_scope(conn, scope)
                for hit in hits:
                    result["evidence_ids"].append(
                        self.evidence(conn, run_id, hit["chunk_id"], hit["preview"], pool)
                    )
                for claim, support in checked:
                    if (
                        not isinstance(claim, dict)
                        or not isinstance(claim.get("text"), str)
                        or not 1 <= len(claim["text"]) <= 2000
                        or not isinstance(claim.get("evidence"), list)
                        or not 1 <= len(claim["evidence"]) <= 5
                    ):
                        raise EngineError("MODEL_OUTPUT_INVALID")
                    evidence_ids = [
                        self.evidence(conn, run_id, item.get("chunk_id"), item.get("quote"), pool)
                        for item in claim["evidence"]
                    ]
                    claim_id = identifier()
                    conn.execute(
                        "INSERT INTO claim_records(id,run_id,text,evidence_ids_json,source_status,model_support,comparability) VALUES(?,?,?,?,'verified',?,'not_assessed')",
                        (
                            claim_id,
                            run_id,
                            claim["text"],
                            json.dumps(evidence_ids),
                            support["status"],
                        ),
                    )
                    result["support_checks"].append({"claim_id": claim_id, **support})
                    conditions = claim.get("conditions", {})
                    if (
                        not isinstance(conditions, dict)
                        or len(conditions) > 10
                        or any(
                            not isinstance(key, str)
                            or len(key) > 100
                            or not isinstance(value, str)
                            or len(value) > 1000
                            for key, value in conditions.items()
                        )
                    ):
                        raise EngineError("MODEL_OUTPUT_INVALID")
                    result["claim_details"].append(
                        {
                            "claim_id": claim_id,
                            "claim_type": "model_draft",
                            "conditions": conditions,
                            "conditions_status": "unverified",
                            "missing_items": [
                                "conditions require human review",
                                "scientific comparability not established",
                            ],
                        }
                    )
                    result["claims"].append(claim_id)
                status = (
                    "completed"
                    if hits
                    and (
                        run["mode"] != "generative"
                        or any(check[1]["status"] == "supported" for check in checked)
                    )
                    else "refused"
                )
                result["outcome"] = (
                    "no_hits"
                    if not hits
                    else "insufficient_evidence"
                    if status == "refused"
                    else "answered"
                    if run["mode"] == "generative"
                    else "evidence_only"
                )
                if status == "refused":
                    result["refusal_reason"] = (
                        "当前文献范围没有检索命中，请调整问题或补充相关文献。"
                        if not hits
                        else "当前候选未形成可发布的获支持草稿。请补充能直接回答问题、包含必要实验条件和数据的原文；模型支持性意见仍需人工核对。"
                    )
                result["evidence_assessment"] = {
                    "source_validation": "exact_current_chunk_quote",
                    "model_support": "same_model_opinion_only",
                    "scientific_quality": "NOT_EVALUATED",
                    "human_review": "separate_persistent_records",
                }
                conn.execute(
                    "UPDATE answer_runs SET status=?,result_json=?,error_code=? WHERE id=?",
                    (
                        status,
                        json.dumps(result),
                        None
                        if status == "completed"
                        else "NO_HITS"
                        if not hits
                        else "INSUFFICIENT_EVIDENCE",
                        run_id,
                    ),
                )
                self.jobs.complete(job["id"], token, "answer_run:" + run_id, connection=conn)
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "ANSWER_FAILED"
            if provider:
                self.generation.providers.mark_error(provider["id"], code)
            self.jobs.fail(job["id"], token, code)
            cancelled = self.jobs.get(job["id"])["status"] == "cancelled"
            failure = (result or {"intent": "literature", "retrieval_status": "not_completed"}) | {
                "kind": "error",
                "outcome": "cancelled"
                if cancelled
                else "system_info_failed"
                if stage == "system_info"
                else "retrieval_failed"
                if stage == "retrieval"
                else "generation_failed",
                "failure_stage": stage,
                "error_code": code,
                "claims": [],
                "evidence_ids": [],
                "support_checks": [],
                "claim_details": [],
                "coverage": "No answer published; diagnostic retrieval metadata only",
            }
            with self.db.transaction() as conn:
                conn.execute(
                    "UPDATE answer_runs SET status=?,error_code=?,result_json=? WHERE id=?",
                    (
                        "cancelled" if cancelled else "failed",
                        code,
                        json.dumps(failure),
                        run_id,
                    ),
                )

        finally:
            for external_generator in external_generators:
                external_generator.close()
            if self.generation.generator is not None:
                self.generation.generator.cancel_check = None

    def public_evidence(self, row):
        value = dict(row)
        anchor = json.loads(value["anchor_json"])
        value["text_origin"] = (
            "ocr_unreviewed"
            if (anchor.get("reason_if_degraded") or "").startswith("OCR_")
            else "docling_layout_table_unreviewed"
            if (anchor.get("reason_if_degraded") or "").startswith("DOCLING_")
            else "native_text_unreviewed"
        )
        value["table_candidates"] = anchor.get("table_candidates", [])
        offsets = anchor["quote_offsets_in_chunk"]
        start = anchor["clean_text_offsets"]["start"]
        value["span"] = {
            "schema_version": "0.1-draft",
            "evidence_id": value["id"],
            **{
                key: anchor[key]
                for key in (
                    "doc_version_id",
                    "file_sha256",
                    "parse_run_id",
                    "source_anchor_id",
                    "page_number",
                    "element_id",
                )
            },
            "quote_text": value["quote"],
            "quote_sha256": hashlib.sha256(value["quote"].encode()).hexdigest(),
            "clean_text_offsets": {
                "start": start + offsets["start"],
                "end": start + offsets["end"],
            },
            "location_confidence": "unknown",
        }
        try:
            self.sources.anchor(value["source_anchor_id"])
            value["current_source_status"] = "verified"
        except EngineError:
            value["current_source_status"] = "stale_or_unavailable"
        with self.db.connection() as conn:
            lifecycle = Lifecycle.source_state(conn, anchor["doc_version_id"])
            value["lifecycle"] = lifecycle
            if lifecycle["state"] != "active":
                value["current_source_status"] = lifecycle["state"]
            value["reviews"] = [
                dict(record)
                for record in conn.execute(
                    "SELECT id,status,note,created_at FROM human_reviews WHERE target_id=? ORDER BY created_at",
                    (value["id"],),
                )
            ]
        return value

    def answers(self, project_id=None, run_id=None):
        with self.db.connection() as conn:
            rows = conn.execute(
                """SELECT r.*,s.versions_json,s.project_id FROM answer_runs r
                JOIN scope_snapshots s ON s.id=r.scope_id WHERE s.project_id IS ? AND (? IS NULL OR r.id=?) ORDER BY r.created_at DESC,r.id DESC LIMIT 30""",
                (project_id, run_id, run_id),
            ).fetchall()
            values = []
            for row in rows:
                value = dict(row)
                value["scope"] = json.loads(value.pop("versions_json"))
                value["result"] = json.loads(value.pop("result_json") or "null")
                value["model_history"] = self.model_history(conn, row["id"])
                value["claims"] = [
                    dict(claim) | {"evidence_ids": json.loads(claim["evidence_ids_json"])}
                    for claim in conn.execute(
                        "SELECT * FROM claim_records WHERE run_id=?", (row["id"],)
                    )
                ]
                value["evidence"] = [
                    self.public_evidence(evidence)
                    for evidence in conn.execute(
                        "SELECT * FROM evidence_records WHERE owner_id=? ORDER BY created_at",
                        (row["id"],),
                    )
                ]
                values.append(value)
            return values

    def create_plan(self, question, fields, versions, project_id, mode):
        if (
            not question.strip()
            or not fields
            or len(fields) > 20
            or any(
                not isinstance(field, str) or not field.strip() or len(field) > 100
                for field in fields
            )
            or len(set(fields)) != len(fields)
            or mode not in {"extractive", "generative"}
        ):
            raise EngineError("INVALID_REQUEST")
        scope = self.freeze(versions, project_id)
        frozen = self.scope(scope)["versions"]
        if len({doc["document_id"] for doc in frozen}) != len(frozen):
            raise EngineError("DUPLICATE_PAPER_VERSIONS", status=409)
        plan_id = identifier()
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO research_plans VALUES(?,?,?,?,?,?,?)",
                (
                    plan_id,
                    scope,
                    question,
                    json.dumps(fields, ensure_ascii=False),
                    mode,
                    "draft",
                    utc_now(),
                ),
            )
            conn.executemany(
                "INSERT INTO research_items(plan_id,doc_version_id,status) VALUES(?,?,'pending')",
                [(plan_id, version) for version in dict.fromkeys(versions)],
            )
        return {"id": plan_id, "status": "draft"}

    def execute_plan(self, plan_id, job_id):
        job = self.jobs.claim(job_id, lease_seconds=1800)
        if not job:
            return
        token = job["lease_token"]
        try:
            with self.db.transaction() as conn:
                plan = dict(
                    conn.execute("SELECT * FROM research_plans WHERE id=?", (plan_id,)).fetchone()
                )
                conn.execute("UPDATE research_plans SET status='running' WHERE id=?", (plan_id,))
            fields = json.loads(plan["fields_json"])
            recorded_fingerprint = None
            for document in self.scope(plan["scope_id"])["versions"]:
                version = document["doc_version_id"]
                try:
                    with self.db.connection() as conn:
                        previous = conn.execute(
                            "SELECT * FROM research_items WHERE plan_id=? AND doc_version_id=?",
                            (plan_id, version),
                        ).fetchone()
                    if (
                        previous["status"] in {"completed", "partial"}
                        and previous["processed_chunks"] == previous["total_chunks"]
                    ):
                        continue
                    self.jobs.heartbeat(job_id, token, seconds=1800)
                    current = Library(self.db).list_documents(
                        self.scope(plan["scope_id"])["project_id"]
                    )
                    if version not in {row["doc_version_id"] for row in current}:
                        raise EngineError("SCOPE_NOT_AVAILABLE")
                    chunks = self.chunks_for(version)
                    if self.current_runs(version) != document["parse_run_ids"]:
                        raise EngineError("SCOPE_STALE")
                    observations = json.loads(previous["observations_json"])
                    checkpoint = previous["processed_chunks"]
                    if checkpoint > len(chunks):
                        raise EngineError("SCOPE_STALE")
                    with self.db.transaction() as conn:
                        self.jobs.require_lease(conn, job_id, token)
                        conn.execute(
                            "UPDATE research_items SET status=?,total_chunks=?,error_code=NULL WHERE plan_id=? AND doc_version_id=?",
                            (
                                "running"
                                if chunks
                                else "needs_ocr"
                                if document["parse_status"] == "partial"
                                else "needs_parse",
                                len(chunks),
                                plan_id,
                                version,
                            ),
                        )
                    if not chunks:
                        continue
                    per_field = {
                        field: sum(value["field"] == field for value in observations)
                        for field in fields
                    }
                    for index, chunk in enumerate(chunks):
                        if index < checkpoint:
                            continue
                        self.jobs.heartbeat(job_id, token, seconds=1800)
                        pool = {chunk["id"]: chunk["clean_text"]}
                        if plan["mode"] == "generative":
                            generator = self.generation.require()
                            if recorded_fingerprint != generator.fingerprint:
                                recorded_fingerprint = self.record_model(
                                    job_id, token, plan_id, generator
                                )
                            generator.cancel_check = lambda: self.cancellation_check(job_id, token)
                            candidates = generator.generate(
                                "research",
                                {
                                    "question": plan["question"],
                                    "fields": fields,
                                    "chunks": [
                                        {"chunk_id": chunk["id"], "text": chunk["clean_text"]}
                                    ],
                                },
                            ).get("observations")
                            if not isinstance(candidates, list) or len(candidates) > 20:
                                raise EngineError("MODEL_OUTPUT_INVALID")
                        else:
                            terms = set(search_terms(chunk["clean_text"]))
                            candidates = [
                                {
                                    "field": field,
                                    "value": chunk["clean_text"][:160],
                                    "unit": "",
                                    "chunk_id": chunk["id"],
                                    "quote": chunk["clean_text"][:600],
                                }
                                for field in fields
                                if set(search_terms(field)) & terms and per_field[field] < 3
                            ]
                        with self.db.transaction() as conn:
                            self.jobs.require_lease(conn, job_id, token)
                            self.require_scope(conn, self.scope(plan["scope_id"]), [version])
                            for candidate in candidates:
                                if not isinstance(candidate, dict):
                                    raise EngineError("MODEL_OUTPUT_INVALID")
                                field = candidate.get("field")
                                if (
                                    field not in fields
                                    or not isinstance(candidate.get("value"), str)
                                    or len(candidate["value"]) > 2000
                                    or not isinstance(candidate.get("unit", ""), str)
                                    or len(candidate.get("unit", "")) > 100
                                ):
                                    raise EngineError("MODEL_OUTPUT_INVALID")
                                evidence_id = self.evidence(
                                    conn,
                                    plan_id,
                                    candidate.get("chunk_id"),
                                    candidate.get("quote"),
                                    pool,
                                )
                                observations.append(
                                    {
                                        **candidate,
                                        "evidence_id": evidence_id,
                                        "model_fingerprint": recorded_fingerprint,
                                        "value_origin": "model_draft"
                                        if plan["mode"] == "generative"
                                        else "excerpt_candidate",
                                        "conditions_status": "not_assessed",
                                        "meaning_status": "reported"
                                        if plan["mode"] == "generative"
                                        else "evidence_insufficient",
                                        "experiment_id": "unassigned",
                                        "conditions": {},
                                        "revision": 0,
                                    }
                                )
                                per_field[field] += 1
                            conn.execute(
                                "UPDATE research_items SET processed_chunks=?,observations_json=? WHERE plan_id=? AND doc_version_id=?",
                                (
                                    index + 1,
                                    json.dumps(observations, ensure_ascii=False),
                                    plan_id,
                                    version,
                                ),
                            )
                    with self.db.transaction() as conn:
                        self.jobs.require_lease(conn, job_id, token)
                        self.require_scope(conn, self.scope(plan["scope_id"]), [version])
                        conn.execute(
                            "UPDATE research_items SET status=? WHERE plan_id=? AND doc_version_id=?",
                            (
                                "partial" if document["parse_status"] != "ready" else "completed",
                                plan_id,
                                version,
                            ),
                        )
                except Exception as item_error:
                    if (
                        self.jobs.get(job_id)["status"] == "cancelled"
                        or isinstance(item_error, EngineError)
                        and item_error.code == "LEASE_LOST"
                    ):
                        raise
                    item_code = (
                        item_error.code
                        if isinstance(item_error, EngineError)
                        else "RESEARCH_ITEM_FAILED"
                    )
                    with self.db.transaction() as conn:
                        self.jobs.require_lease(conn, job_id, token)
                        conn.execute(
                            "UPDATE research_items SET status='failed',error_code=? WHERE plan_id=? AND doc_version_id=?",
                            (item_code, plan_id, version),
                        )
            with self.db.transaction() as conn:
                self.jobs.require_lease(conn, job_id, token)
                incomplete = conn.execute(
                    "SELECT COUNT(*) FROM research_items WHERE plan_id=? AND status!='completed'",
                    (plan_id,),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE research_plans SET status=? WHERE id=?",
                    ("partial" if incomplete else "completed", plan_id),
                )
                self.jobs.complete(job_id, token, "research_plan:" + plan_id, connection=conn)
        except Exception as exc:
            code = exc.code if isinstance(exc, EngineError) else "RESEARCH_FAILED"
            self.jobs.fail(job_id, token, code)
            state = "cancelled" if self.jobs.get(job_id)["status"] == "cancelled" else "failed"
            with self.db.transaction() as conn:
                conn.execute("UPDATE research_plans SET status=? WHERE id=?", (state, plan_id))
                conn.execute(
                    "UPDATE research_items SET status=?,error_code=? WHERE plan_id=? AND status='running'",
                    (state, code, plan_id),
                )

        finally:
            if self.generation.generator is not None:
                self.generation.generator.cancel_check = None

    def plans(self, project_id=None, plan_id=None):
        with self.db.connection() as conn:
            conn.execute("BEGIN")
            rows = conn.execute(
                """SELECT p.*,s.versions_json FROM research_plans p JOIN scope_snapshots s ON s.id=p.scope_id
                WHERE s.project_id IS ? AND (? IS NULL OR p.id=?) ORDER BY p.created_at DESC LIMIT 30""",
                (project_id, plan_id, plan_id),
            ).fetchall()
            output = []
            for row in rows:
                plan = dict(row)
                plan["fields"] = json.loads(plan.pop("fields_json"))
                plan["scope"] = json.loads(plan.pop("versions_json"))
                plan["model_history"] = self.model_history(conn, row["id"])
                plan["scope_warnings"] = []
                for document in plan["scope"]:
                    current = conn.execute(
                        "SELECT document_id FROM document_versions WHERE id=?",
                        (document["doc_version_id"],),
                    ).fetchone()
                    if (
                        not document.get("document_id")
                        or not current
                        or current[0] != document["document_id"]
                    ):
                        plan["scope_warnings"].append(
                            {
                                "doc_version_id": document["doc_version_id"],
                                "title": document["title"],
                                "code": "SCOPE_IDENTITY_CHANGED",
                            }
                        )
                plan["source_warnings"] = [
                    {
                        "doc_version_id": doc["doc_version_id"],
                        **Lifecycle.source_state(conn, doc["doc_version_id"]),
                    }
                    for doc in plan["scope"]
                    if Lifecycle.source_state(conn, doc["doc_version_id"])["state"] != "active"
                ]
                plan["items"] = [
                    dict(item) | {"observations": json.loads(item["observations_json"])}
                    for item in conn.execute(
                        "SELECT * FROM research_items WHERE plan_id=?", (row["id"],)
                    )
                ]
                plan["evidence"] = [
                    self.public_evidence(item)
                    for item in conn.execute(
                        "SELECT * FROM evidence_records WHERE owner_id=?", (row["id"],)
                    )
                ]
                plan["reports"] = [
                    dict(item)
                    for item in conn.execute(
                        "SELECT * FROM report_revisions WHERE plan_id=? ORDER BY revision DESC",
                        (row["id"],),
                    )
                ]
                plan["coverage"] = {
                    state: sum(item["status"] == state for item in plan["items"])
                    for state in (
                        "pending",
                        "running",
                        "completed",
                        "partial",
                        "failed",
                        "cancelled",
                        "needs_parse",
                        "needs_ocr",
                    )
                }
                output.append(plan)
            return output

    def review(self, target, status, note):
        if (
            status not in {"unreviewed", "confirmed", "rejected"}
            or not isinstance(note, str)
            or len(note) > 4000
        ):
            raise EngineError("INVALID_REVIEW")
        with self.db.transaction() as conn:
            table = (
                "claim_records"
                if conn.execute("SELECT 1 FROM claim_records WHERE id=?", (target,)).fetchone()
                else "evidence_records"
            )
            if not conn.execute(f"SELECT 1 FROM {table} WHERE id=?", (target,)).fetchone():
                raise EngineError("NOT_FOUND", status=404)
            conn.execute(f"UPDATE {table} SET human_status=? WHERE id=?", (status, target))
            if table == "evidence_records":
                conn.execute("UPDATE evidence_records SET review_note=? WHERE id=?", (note, target))
            snapshot = dict(conn.execute(f"SELECT * FROM {table} WHERE id=?", (target,)).fetchone())
            conn.execute(
                "INSERT INTO human_reviews VALUES(?,?,?,?,?,?)",
                (
                    identifier(),
                    target,
                    status,
                    note,
                    utc_now(),
                    json.dumps({"actor": "local_user", "record": snapshot}, ensure_ascii=False),
                ),
            )
        return {"target_id": target, "human_status": status}

    def edit_observation(self, plan_id, evidence_id, value):
        allowed_conditions = {
            "method",
            "dataset",
            "population",
            "sample_size",
            "metric",
            "split",
            "experimental_conditions",
            "unit",
        }
        if (
            not isinstance(value.get("conditions"), dict)
            or not set(value["conditions"]).issubset(allowed_conditions)
            or any(
                not isinstance(text, str) or len(text) > 1000
                for text in value["conditions"].values()
            )
        ):
            raise EngineError("INVALID_REQUEST")
        with self.db.transaction() as conn:
            rows = conn.execute(
                "SELECT * FROM research_items WHERE plan_id=?", (plan_id,)
            ).fetchall()
            found = None
            for row in rows:
                observations = json.loads(row["observations_json"])
                for index, observation in enumerate(observations):
                    if observation["evidence_id"] == evidence_id:
                        found = (row, observations, index, observation)
                        break
            if found is None:
                raise EngineError("NOT_FOUND", status=404)
            row, observations, index, before = found
            if before.get("revision", 0) != value["expected_revision"]:
                raise EngineError("REVIEW_CONFLICT", status=409)
            if conn.execute(
                "SELECT 1 FROM research_plans WHERE id=? AND status='running'", (plan_id,)
            ).fetchone():
                raise EngineError("WORKER_BUSY", status=429)
            after = {
                **before,
                **{key: item for key, item in value.items() if key != "expected_revision"},
                "revision": before.get("revision", 0) + 1,
                "value_origin": "human_edited",
            }
            observations[index] = after
            conn.execute(
                "UPDATE research_items SET observations_json=? WHERE plan_id=? AND doc_version_id=?",
                (json.dumps(observations, ensure_ascii=False), plan_id, row["doc_version_id"]),
            )
            conn.execute(
                "UPDATE evidence_records SET human_status='unreviewed' WHERE id=?", (evidence_id,)
            )
            conn.execute(
                "INSERT INTO observation_revisions VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    identifier(),
                    plan_id,
                    row["doc_version_id"],
                    evidence_id,
                    after["revision"],
                    json.dumps(before, ensure_ascii=False),
                    json.dumps(after, ensure_ascii=False),
                    "local_user",
                    utc_now(),
                ),
            )
        return after

    def report(self, plan_id):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT s.project_id FROM research_plans p JOIN scope_snapshots s ON s.id=p.scope_id WHERE p.id=?",
                (plan_id,),
            ).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        plan = next(item for item in self.plans(row[0], plan_id) if item["id"] == plan_id)

        if plan["status"] == "running":
            raise EngineError("WORKER_BUSY", status=429)

        def safe(value):
            text = str(value).replace("<", "&lt;").replace(">", "&gt;").replace("\n", " ")
            return "".join("\\" + char if char in "\\`*_{}[]()!#+|" else char for char in text)

        lines = [
            "# Research 证据整理报告",
            "",
            "生成时间：" + utc_now(),
            "本报告是生成时的快照；来源随后可能过期，导出前请创建新修订以重新核对。",
            "",
            "问题：" + safe(plan["question"]),
            "",
            f"冻结文献数：{len(plan['scope'])}；处理状态：{json.dumps(plan['coverage'], ensure_ascii=False)}",
            "",
            "本报告是证据整理草稿。摘录候选或模型草稿不代表科学结论；缺少提取不能解释为原文未报告。",
            "",
            "| 文献 | 字段 | 值/摘录 | 单位 | 人工状态 | 来源 |",
            "|---|---|---|---|---|---|",
        ]
        lines.extend(
            [
                "",
                "实验条件、单位、数据集和划分未核对时不进行跨论文排序。确认/否定是人工记录；当前来源失效须重新核对。",
                "",
            ]
        )
        if plan.get("scope_warnings"):
            lines.extend(
                [
                    "范围警告：冻结后文献身份已变化或旧快照未记录身份，不能把本报告计数作为当前去重论文数；请新建计划。",
                    safe(json.dumps(plan["scope_warnings"], ensure_ascii=False)),
                    "",
                ]
            )
        if plan.get("source_warnings"):
            lines.extend(
                [
                    "来源警告：部分论文已停用、人工标记撤稿或不可用，不能用于新的科研结论。",
                    safe(json.dumps(plan["source_warnings"], ensure_ascii=False)),
                    "",
                ]
            )
        evidence = {row["id"]: row for row in plan["evidence"]}
        lines.extend(
            [
                "模型调用记录（包括失败/取消尝试，不代表抽取成功）：",
                safe(json.dumps(plan["model_history"], ensure_ascii=False)),
                "",
            ]
        )
        for item in plan["items"]:
            title = next(
                doc["title"]
                for doc in plan["scope"]
                if doc["doc_version_id"] == item["doc_version_id"]
            )
            for field in plan["fields"]:
                observations = [value for value in item["observations"] if value["field"] == field]
                if not observations:
                    lines.append(
                        "| "
                        + " | ".join(
                            map(safe, [title, field, "未提取（非未报告）", "", item["status"], ""])
                        )
                        + " |"
                    )
                for value in observations:
                    record = evidence[value["evidence_id"]]
                    anchor = json.loads(record["anchor_json"])
                    lines.append(
                        "| "
                        + " | ".join(
                            map(
                                safe,
                                [
                                    title,
                                    field,
                                    value["value"]
                                    + "；实验="
                                    + value.get("experiment_id", "unassigned")
                                    + "；条件="
                                    + json.dumps(value.get("conditions", {}), ensure_ascii=False)
                                    + "；可比性="
                                    + value.get("conditions_status", "not_assessed")
                                    + "；抽取模型="
                                    + json.dumps(
                                        value.get("model_fingerprint"), ensure_ascii=False
                                    ),
                                    value.get("unit", ""),
                                    record["human_status"]
                                    + "/"
                                    + record["current_source_status"]
                                    + "/"
                                    + value.get("meaning_status", "evidence_insufficient")
                                    + "/"
                                    + record["text_origin"],
                                    f"第{anchor['page_number']}页 / {record['source_anchor_id']}"
                                    + (
                                        "；表格候选（结构待核对）="
                                        + json.dumps(record["table_candidates"], ensure_ascii=False)
                                        if record["table_candidates"]
                                        else ""
                                    ),
                                ],
                            )
                        )
                        + " |"
                    )
        report_id = identifier()
        with self.db.transaction() as conn:
            revision = conn.execute(
                "SELECT COALESCE(MAX(revision),0)+1 FROM report_revisions WHERE plan_id=?",
                (plan_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO report_revisions VALUES(?,?,?,?,?)",
                (report_id, plan_id, revision, "\n".join(lines), utc_now()),
            )
        return {"id": report_id, "revision": revision}

    def report_content(self, report_id):
        with self.db.connection() as conn:
            row = conn.execute("SELECT * FROM report_revisions WHERE id=?", (report_id,)).fetchone()
        if row is None:
            raise EngineError("NOT_FOUND", status=404)
        value = dict(row)
        with self.db.connection() as conn:
            scope = conn.execute(
                "SELECT s.versions_json FROM research_plans p JOIN scope_snapshots s ON s.id=p.scope_id WHERE p.id=?",
                (value["plan_id"],),
            ).fetchone()
            warnings = []
            for document in json.loads(scope[0]):
                version = document["doc_version_id"]
                state = Lifecycle.source_state(conn, version)
                current = sorted(
                    row[0]
                    for row in conn.execute(
                        "SELECT DISTINCT e.parse_run_id FROM published_pages p JOIN elements e ON e.id=p.element_id WHERE p.doc_version_id=?",
                        (version,),
                    )
                )
                identity = conn.execute(
                    "SELECT document_id FROM document_versions WHERE id=?", (version,)
                ).fetchone()
                identity_changed = (
                    not identity
                    or not document.get("document_id")
                    or identity[0] != document["document_id"]
                )
                if (
                    state["state"] != "active"
                    or current != document["parse_run_ids"]
                    or identity_changed
                ):
                    warnings.append(
                        {
                            "doc_version_id": version,
                            **state,
                            "parse_changed": current != document["parse_run_ids"],
                            "identity_changed": identity_changed,
                        }
                    )
        value["source_warnings"] = warnings
        value["export_body"] = (
            (
                "来源状态提示（导出时核查，不改写历史修订）：部分来源停用、撤稿或解析已变化，请复核。\n\n"
                + json.dumps(warnings, ensure_ascii=False).replace("<", "&lt;").replace(">", "&gt;")
                + "\n\n"
            )
            if warnings
            else ""
        ) + value["body"]
        return value
