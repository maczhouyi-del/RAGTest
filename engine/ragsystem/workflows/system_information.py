"""Exact allowlist for runtime questions; not a general topic classifier or an LLM."""

import re
import unicodedata

FORMS = {
    "generation": (
        "你是什么模型",
        "当前是什么模型",
        "当前使用的是什么模型",
        "当前使用的生成模型是什么",
        "当前用的什么模型",
        "现在是什么模型",
        "当前生成模型是什么",
        "现在使用什么生成模型",
        "你使用的是什么模型",
        "你用的什么模型",
        "当前使用什么模型",
        "现在用的是什么模型",
        "what model are you",
        "what is the current generation model",
        "what model are you using",
        "which model are you using",
        "what is the current model",
    ),
    "embedding": (
        "现在使用什么Embedding模型",
        "当前Embedding模型是什么",
        "当前使用的Embedding模型是什么",
        "现在用的是什么Embedding模型",
        "使用的Embedding模型是什么",
        "what is the current embedding model",
        "what embedding model are you using",
    ),
    "index": (
        "当前向量索引是否就绪",
        "向量索引就绪了吗",
        "当前向量索引状态是什么",
        "is the vector index ready",
        "what is the current vector index status",
    ),
    "retrieval": (
        "当前使用什么检索策略",
        "当前检索策略是什么",
        "现在用什么检索策略",
        "what retrieval strategy are you using",
        "what is the current retrieval strategy",
    ),
}


def normalize(value):
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", value).lower()
        if not char.isspace() and not unicodedata.category(char).startswith("P")
    )


def system_question_forms():
    return {topic: [normalize(value) for value in values] for topic, values in FORMS.items()}


def system_information_topic(question):
    query = normalize(question)
    return next(
        (topic for topic, values in system_question_forms().items() if query in values), None
    )


def question_parts(question):
    """Only split at explicit clause boundaries and only remove exact allowlisted clauses.

    Unrecognized/ambiguous wording stays intact for literature retrieval and generation.
    No topic-keyword heuristic may discard part of a scientific question.
    """
    topic = system_information_topic(question)
    if topic:
        return [topic], ""
    clauses = re.split(
        r"[？?！!。;；\n,，]+|以及|并且|同时|并|\band\b|\balso\b", question, flags=re.I
    )
    topics, literature = [], []
    for clause in clauses:
        clause = clause.strip()
        if not clause:
            continue
        topic = system_information_topic(clause)
        if topic:
            if topic not in topics:
                topics.append(topic)
        else:
            literature.append(clause)
    # When nothing matched, preserve the entire original wording, including punctuation.
    return (topics, "；".join(literature)) if topics else ([], question)


def runtime_information(work, topic, selection, strategy="keyword"):
    if topic in {"embedding", "index", "retrieval"}:
        value = work.search.status()
        configuration = {
            key: value[key]
            for key in ("configured", "ready", "reason", "model", "backend", "generation")
        }
        configuration["model_role"] = "embedding"
        embedding_text = (
            f"当前 Embedding 配置为 {value['model']}，索引{'已就绪' if value['ready'] else '需要建立或更新'}。"
            if value["configured"]
            else "尚未配置 Embedding 模型；当前可以使用关键词检索。"
        )
        if topic == "retrieval":
            configuration["selected_strategy"] = strategy
            configuration["executed_strategy"] = None
            text = f"当前问答选择的检索策略为 {strategy}。{embedding_text}此系统信息未执行检索。"
        elif topic == "index":
            text = f"当前向量索引{'已就绪' if value['ready'] else '未就绪'}。{embedding_text}"
        else:
            text = embedding_text + "Embedding 用于检索编码，不是生成回答的模型。"
    elif selection == "extractive":
        configuration = {"mode": "extractive", "model": None}
        text = "当前问答使用原文摘录模式，不调用生成模型。"
    elif selection == "local":
        value = work.generation.status()
        model = value["fingerprint"].get("model") if value["fingerprint"] else None
        configuration = {
            "mode": "local",
            "model": model,
            "configured": value["configured"],
            "loaded": value["loaded"],
        }
        text = (
            f"当前选择的本地生成模型为 {model}，资源已配置，{'已加载' if value['loaded'] else '尚未加载'}。"
            if value["configured"]
            else "当前选择本地生成模型，但尚未配置模型资源。"
        )
    else:
        row = work.generation.providers.get(selection)
        value = work.generation.providers.public(row)
        configuration = {
            key: value[key]
            for key in (
                "id",
                "name",
                "model",
                "revision",
                "document_qa_enabled",
                "credential_available",
                "can_answer",
                "configured",
                "saved",
                "connection_verified",
                "generation_verified",
            )
        }
        configuration["mode"] = "provider"
        configuration["remote_health_checked"] = False
        credential = (
            "本机网关认证"
            if row["kind"] == "magpie"
            else "显式无需认证"
            if row["auth_mode"] == "none"
            else "当前会话有凭据"
            if value["credential_available"]
            else "需重新输入凭据"
        )
        text = f"当前选择的生成模型配置为 {row['name']} 的 {row['model']}；文献问答{'已启用' if value['document_qa_enabled'] else '未启用'}，{credential}。"
    configuration["inference_performed"] = False
    return {
        "kind": "system_info",
        "intent": "system_info",
        "system_topic": topic,
        "text": text + "此系统信息仅读取本机配置，未调用生成模型。",
        "configuration": configuration,
        "coverage": "runtime configuration only; no scientific evidence",
    }
