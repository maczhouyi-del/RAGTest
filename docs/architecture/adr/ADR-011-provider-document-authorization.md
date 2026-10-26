# ADR-011 Provider 配置级文献问答授权

状态：用户于2026-10-26明确授权实施；不表示平台或科研验收签字。

替代ADR-010及MVP-02中“每次问答传allow_external授权”的交互与校验部分。只保留必要问题/最近最多3轮有界上下文/本轮片段，可能计费，不上传完整PDF，不自动换服务，API Key仍只在引擎会话内存。

generation_provider_authorizations记录provider_id、provider_revision、enabled、updated_at；迁移18不自动授权历史连接。保存并启用或专门开关是显式授权操作。关键配置kind/base_url/model/vendor/auth_mode/output_mode/token_parameter改变，普通保存使授权失效；明确“保存并启用”可授权该新修订。同配置仅重输密钥/重命名保留授权并重新绑定修订。跨地址不复用会话密钥。

后端在排队及每次NetworkProvider文献请求前重新检查数据库授权、修订与凭据；旧allow_external只保留输入兼容，不能授予权限。模型列表检查不发送文献，不依赖文献问答授权。关闭开关会阻止后续请求，已经发出的文本无法撤回。重启保留非敏感授权，清空Key/验证状态；需认证服务无Key时can_answer=false（显式本机无需认证模式及本地GGUF不需Key）。

风险/回退：授权适用于同修订后续问答，需在设置清楚说明发送范围并提供关闭入口；旧客户端应先调用授权端点，否则fail-closed。回退代码必须保留迁移前备份、拒绝高schema，不删除授权/用户数据。本决策不改变引用真实性、支持性、科研质量或检索排序。
