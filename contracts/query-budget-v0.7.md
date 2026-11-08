# 查询输入预算补充 v0.7

兼容既有IPC形状/迁移，无schema更改。字符上限仍是传输与UI约束，不代表可放入512 Token模型。

E5预算包括`query: `前缀与特殊Token：≤512可编码，>512返回QUERY_CONTEXT_LIMIT；文档仍使用EMBEDDING_CONTEXT_LIMIT，绝不静默截断。锁定tokenizer与EmbeddingSpace预处理/指纹不变。

对话向量/混合查询保留完整当前问题；仅显式指代时按原规则取最近两轮问题，并从最旧轮开始移除以满足预算。result.context_policy记录retrieval_query、query_token_limit、dropped_history_turns及v4策略版本。keyword不使用向量Token限制。当前问题本身溢出则明确失败，不更改已发布索引，不自动切换模型或云服务。
