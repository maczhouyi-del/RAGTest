import re

TOKENIZER_VERSION = "cjk-bigrams-latin-v1"


def search_terms(text):
    output = []
    for token in re.findall(r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+", text.lower()):
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            output.extend(token[index : index + 2] for index in range(max(1, len(token) - 1)))
        else:
            output.append(token)
    return list(dict.fromkeys(output))


def index_terms(conn, chunk_id, text):
    if not conn.execute(
        "SELECT 1 FROM terms_indexed_chunks WHERE chunk_id=?", (chunk_id,)
    ).fetchone():
        conn.execute(
            "INSERT INTO chunks_terms_v1 VALUES(?,?)", (chunk_id, " ".join(search_terms(text)))
        )
        conn.execute("INSERT INTO terms_indexed_chunks VALUES(?)", (chunk_id,))
