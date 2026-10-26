"""Exact allowlist for runtime questions; not a general topic classifier or an LLM."""

import re
import unicodedata

FORMS = {
    "generation": (
        "你是什么模型",
        "当前生成模型是什么",
        "现在使用什么生成模型",
        "你使用的是什么模型",
        "你用的什么模型",
        "当前使用什么模型",
        "现在用的是什么模型",
        "what model are you",
        "what is the current generation model",
    ),
    "embedding": (
        "现在使用什么Embedding模型",
        "当前Embedding模型是什么",
        "当前使用的Embedding模型是什么",
        "现在用的是什么Embedding模型",
        "使用的Embedding模型是什么",
        "what is the current embedding model",
    ),
}


def normalize(value):
    return re.sub(r"[\s？?！!。.]+", "", unicodedata.normalize("NFKC", value).lower())


def system_question_forms():
    return {topic: [normalize(value) for value in values] for topic, values in FORMS.items()}


def system_information_topic(question):
    query = normalize(question)
    return next(
        (topic for topic, values in system_question_forms().items() if query in values), None
    )


def runtime_information(work, topic, selection):
    if topic == "embedding":
        value = work.search.status()
        configuration = {
            key: value[key] for key in ("configured", "ready", "model", "backend", "generation")
        }
        text = (
            f"当前 Embedding 配置为 {value['model']}，索引{'已就绪' if value['ready'] else '需要建立或更新'}。"
            if value["configured"]
            else "尚未配置 Embedding 模型；当前可以使用关键词检索。"
        )
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
            f"当前选择的本地生成模型为 {model}，资源已配置。"
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
            )
        }
        configuration["mode"] = "provider"
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
    return {
        "kind": "system_info",
        "intent": "system_info",
        "system_topic": topic,
        "text": text,
        "configuration": configuration,
        "coverage": "runtime configuration only; no scientific evidence",
    }
