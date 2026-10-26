# MVP v0.4 本地增量契约（2026-10-26）

基于v0.3及MVP-02，仍为受认证本机IPC，传输握手版本不变。用户明确批准本次授权语义变更（ADR-011）。

## Provider授权（A）

SQLite schema18新增generation_provider_authorizations；历史Provider默认未启用。POST /v0/generation-providers新增enable_for_documents: true/false/null，true为明确保存并启用，false禁用，null仅同关键配置时保留原授权。POST /v0/generation-providers/{id}/authorization接收expected_revision与enabled，无网络副作用，可在缺Key时保存非敏感授权。配置关键字段变更使旧授权无效，显式重启用才能调用；跨地址不复用凭据。

列表新增document_qa_enabled、authorization_revision、can_answer；configured继续表示会话凭据/显式无需认证是否可用，不能单独代表文献问答已启用。持久授权不等于会话Key或实际连接/生成能力已验证。旧answer请求allow_external布尔保留兼容但不再授权；provider_revision仍需匹配。缺持久授权返回PROVIDER_DOCUMENT_QA_DISABLED；修订变化PROVIDER_CHANGED；缺凭据PROVIDER_CREDENTIALS_REQUIRED。后端逐次网络请求复核，不能只依赖前端。
