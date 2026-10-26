# MVP v0.4 本地增量契约（2026-10-26）

基于v0.3及MVP-02，仍为受认证本机IPC，传输握手版本不变。用户明确批准本次授权语义变更（ADR-011）。

## Provider授权（A）

SQLite schema18新增generation_provider_authorizations；历史Provider默认未启用。POST /v0/generation-providers新增enable_for_documents: true/false/null，true为明确保存并启用，false禁用，null仅同关键配置时保留原授权。POST /v0/generation-providers/{id}/authorization接收expected_revision与enabled，无网络副作用，可在缺Key时保存非敏感授权。配置关键字段变更使旧授权无效，显式重启用才能调用；跨地址不复用凭据。

列表新增document_qa_enabled、authorization_revision、can_answer；configured继续表示会话凭据/显式无需认证是否可用，不能单独代表文献问答已启用。持久授权不等于会话Key或实际连接/生成能力已验证。旧answer请求allow_external布尔保留兼容但不再授权；provider_revision仍需匹配。缺持久授权返回PROVIDER_DOCUMENT_QA_DISABLED；修订变化PROVIDER_CHANGED；缺凭据PROVIDER_CREDENTIALS_REQUIRED。后端逐次网络请求复核，不能只依赖前端。

## 最小系统信息与当前证据（B）

GET /v0/health新增system_question_forms，前端仅据该白名单开放无文献/无生成配置的系统提问；后端仍独立严格匹配。POST /v0/answers的version_ids可缺省为空，但仅系统信息分支接受；普通文献问答继续要求有效冻结范围。系统信息run保存空scope，不经过检索、生成、外部授权检查或科学支持性判定；result.kind/intent=system_info，带system_topic、确定性text及非敏感configuration，没有claim/evidence。系统问答不进入后续论文检索的有界历史上下文。

文献result增加intent=literature、retrieval_status=hits/no_hits，不改变引用真实性或支持性规则。前端新提交立即清除当前证据；selectedId未加载时不回退其他run。右侧仅展示当前run的evidence；拒答命中标记候选而非已支持结论，生成失败与无命中分别展示。既有run缺少新字段时仍可读取，按原status/result.kind保守显示。
