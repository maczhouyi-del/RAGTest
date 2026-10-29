import re
import unicodedata

TOKENIZER_VERSION = "cjk-unigrams-bigrams-tf-v2"


def tokenize(text, *, unigrams=False):
    output = []
    for token in re.findall(
        r"[\u3400-\u9fff]+|[^\W_\u3400-\u9fff]+", unicodedata.normalize("NFKC", text).casefold()
    ):
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            if unigrams and len(token) > 1:
                output.extend(token)
            output.extend(token[index : index + 2] for index in range(max(1, len(token) - 1)))
        else:
            output.append(token)
    return output


def search_terms(text):
    return list(dict.fromkeys(tokenize(text)))


def quoted_phrases(text):
    phrases = []
    for match in re.finditer(
        r'"([^"\n]{2,200})"|“([^”\n]{2,200})”', unicodedata.normalize("NFKC", text)
    ):
        phrase = next(value for value in match.groups() if value is not None).strip()
        if phrase and tokenize(phrase) and phrase not in phrases:
            phrases.append(phrase)
        if len(phrases) == 3:
            break
    return phrases


def index_terms(conn, chunk_id, text):
    if not conn.execute(
        "SELECT 1 FROM terms_indexed_chunks_v2 WHERE chunk_id=?", (chunk_id,)
    ).fetchone():
        conn.execute(
            "INSERT INTO chunks_terms_v2 VALUES(?,?)",
            (chunk_id, " ".join(tokenize(text, unigrams=True))),
        )
        conn.execute("INSERT INTO terms_indexed_chunks_v2 VALUES(?)", (chunk_id,))
