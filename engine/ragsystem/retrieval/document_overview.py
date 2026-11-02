"""Bounded, source-backed section retrieval for single-document overview questions.

This supplements literal/semantic search with document structure; it never supplies
an answer, expands scope, or treats a section as scientifically verified.
"""

import re

from ragsystem.retrieval.source_search import Sources


def overview_topic(question):
    if re.search(r"(?:两篇|两份|这两|文献|论文).*(?:相似|共同|异同|区别)|\b(?:similarities|differences)\b.*\b(?:papers|documents)\b", question, re.I):
        return "comparison"
    if re.search(r"主要(?:的)?贡献|核心(?:的)?贡献|创新点|主要创新|\b(?:main|major|key|principal) contributions?\b", question, re.I):
        return "contributions"
    if re.search(r"(?:主要)?解决(?:了)?(?:什么|哪些|的).*问题|研究目的|研究目标|\b(?:what|which) (?:problem|problems).*?(?:solve|address)|\b(?:main|primary) (?:problem|objective)\b", question, re.I):
        return "problem"
    if re.search(r"主要(?:的)?方法|核心(?:的)?方法|采用.*什么方法|\b(?:main|primary) (?:method|approach)\b", question, re.I):
        return "method"
    return None


def section_candidates(db, versions, project_id, topic):
    if topic not in {"contributions", "problem", "comparison", "method"} or len(versions) != 1:
        return []
    with db.connection() as conn:
        conn.execute("BEGIN")
        Sources.require_scope(conn, versions, project_id)
        rows = [dict(row) for row in conn.execute(
            "SELECT c.* FROM chunks c JOIN document_versions v ON v.id=c.doc_version_id "
            "WHERE c.visible=1 AND v.visibility='visible' AND c.doc_version_id=? "
            "ORDER BY c.page_number,c.start_offset,c.id", (versions[0],)
        )]
    scored = {}
    in_references = False
    abstract_page, abstract_chars = None, 0
    for index, row in enumerate(rows):
        text = row['clean_text'].replace('\ufffe', '').replace('\u00ad', '')
        text = re.sub(r'(?<=\w)-\s*\n\s*(?=\w)', '', text)
        if re.search(r"(?im)^\s*(?:\d+[. ]+)?(?:references|bibliography|参考文献)\s*$", text):
            in_references = True
        # Appendices are still excluded from this overview lane; ordinary search
        # remains available for questions specifically about references/appendices.
        if in_references:
            continue
        abstract = re.search(r"(?im)^[ \t]*(?:abstract|摘要)(?:[ \t]*[:：][ \t]*|[ \t]*\r?$)", text)
        if abstract:
            abstract_page, abstract_chars = row['page_number'], 0
        in_abstract = abstract_page is not None and row['page_number'] <= abstract_page + 1 and abstract_chars < 6000
        ending = re.search(r"(?im)^[ \t]*(?:keywords?\s*[:：]|关键词|(?:\d+[. ]+)?introduction\b|(?:\d+[. ]+)?引言)", text)
        body = text[abstract.end():] if abstract else text
        if ending:
            body = body[:max(0, ending.start() - (abstract.end() if abstract else 0))]
        abstract_score = 0
        if in_abstract and len(body.strip()) > 30:
            abstract_score = 85 if len(body.strip()) > 120 else 70
            # Prioritize actual abstract statements over authors/affiliations or
            # an isolated heading when legacy chunks are very short.
            if re.search(r"\bwe\s+(?:propose|hypothesi[sz]ed|present|introduce)|(?:results?|findings?)\s+(?:suggest|show|demonstrate)|本文.*(?:提出|表明)", body, re.I):
                abstract_score += 10
        abstract_chars += len(body)
        if ending:
            abstract_page = None
        contribution = re.search(r"(?:contributions?\s+(?:of\s+(?:our|this)\s+(?:paper|work)\s+)?(?:are|is)|(?:our|main|major|key)\s+contributions?|本文.*贡献)", text, re.I)
        problem = re.search(r"(?:major|main|primary)\s+(?:limitation|problem)|(?:we|this paper)\s+(?:address|aim|propose)|主要.*(?:问题|局限)|本文.*(?:解决|旨在)", text, re.I)
        conclusion = re.search(r"(?im)^\s*(?:\d+[. ]+)?(?:conclusions?|结论)\s*$", text)
        method = re.search(r"(?im)^\s*(?:\d+[. ]+)?(?:materials and methods|methods?|methodology|方法)\s*$", text)
        score = max(abstract_score, 100 if topic == 'contributions' and contribution else 0,
                    100 if topic == 'problem' and problem else 0, 90 if topic == 'method' and method else 0, 60 if conclusion else 0)
        if score:
            scored[index] = max(scored.get(index, 0), score)
            if not in_abstract and index + 1 < len(rows) and rows[index + 1]['page_number'] == row['page_number']:
                # Preserve the continuation when a heading/list is split by chunking.
                scored[index + 1] = max(scored.get(index + 1, 0), score - 5)
    ranked = sorted(scored, key=lambda i: (-scored[i], rows[i]['page_number'], rows[i]['start_offset'], rows[i]['id']))
    return [{
        'doc_version_id': rows[i]['doc_version_id'], 'chunk_id': rows[i]['id'],
        'source_anchor_id': rows[i]['id'], 'page_number': rows[i]['page_number'],
        'preview': rows[i]['clean_text'], 'content_sha256': rows[i]['content_sha256'],
        'rank': n + 1, 'section_priority': scored[i], 'retrieval_lane': 'document_overview_sections',
        'location_confidence': 'unknown',
    } for n, i in enumerate(ranked[:12])]
