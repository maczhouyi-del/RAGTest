"""Resolve explicit paper names only inside the caller's existing scope."""

import re
import unicodedata

from ragsystem.library.repository import Library


def normalized(value):
    return ''.join(c for c in unicodedata.normalize('NFKC', value).casefold() if c.isalnum())


def named_versions(db, question, versions, project_id):
    query = normalized(question)
    full, aliases = set(), set()
    for row in Library(db).list_documents(project_id):
        version = row['doc_version_id']
        if version not in versions:
            continue
        title = row['title']
        name = normalized(title)
        # Full titles are preferred to short aliases. Neither expands scope.
        if len(name) >= 8 and name in query:
            full.add(version)
        prefix = re.split(r'[:：]', title, maxsplit=1)[0].strip()
        if re.fullmatch(r'[A-Za-z][A-Za-z0-9-]{2,19}', prefix) and re.search(
            r'(?<![A-Za-z0-9])' + re.escape(prefix) + r'(?![A-Za-z0-9])', question, re.I
        ):
            aliases.add(version)
    matches = full or aliases
    return [version for version in versions if version in matches]
