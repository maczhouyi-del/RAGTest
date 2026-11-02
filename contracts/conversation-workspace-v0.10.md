# CHAT-01 对话工作区契约 v0.10

2026-11-01；本次用户批准的四项功能增量。保持 `/v0` 与 0.1.0 握手；新增端点及字段向后兼容读取，远程配置多记录写入语义按本次产品要求收紧。SQLite schema20，旧程序必须拒绝打开高版本库。

## 对话生命周期

- 新增迁移0019，`conversations.archived_at`、`renamed_at` 可空。归档保留消息、引用和研究记录；手动名称不会被第一轮自动题名覆盖。
- `GET /v0/history/conversations` 默认未归档；`GET /v0/history/archived_conversations` 独立归档集合。两者保持 `project_id IS ?`、`updated_at DESC,id DESC` 与原有有界游标格式；重命名/归档不伪造对话活动时间。
- `POST /v0/conversations/{uuid}/manage` 接收 `action=rename|archive|restore|delete`、可空 `project_id`，rename还需trim后1–160字符的title。作用域不匹配返回NOT_FOUND。
- 删除在同一个SQLite写事务中检查任务。非completed/failed/cancelled状态或仍有租约返回409 CONVERSATION_BUSY，不取消后立即抢删。任务领取/新问答与删除由写锁隔离。
- 研究修订仍引用会话证据时返回409 CONVERSATION_REFERENCED，避免破坏研究可追溯性。其他情况仅删除该会话所属问答、结论、证据、人工复核、无共享引用的终结任务/事件/attempt和scope。不触碰PDF、document/version、解析、Chunk、Embedding、索引或其他会话。
- Tauri `manage_conversation` 校验UUID、动作及长度后转发；前端 `manageConversation` 只调用真实持久化API。删除必须经界面确认；当前会话删除/归档后回到问答首页。

## 一个有效远程配置

- 新增迁移0020：`generation_providers.retired_at`；常量唯一索引 `one_active_remote_provider ON generation_providers((1)) WHERE retired_at IS NULL`，api/Magpie合计最多一个有效连接。本地Qwen与原文摘录不在此表，不受影响。
- 旧库按 `updated_at DESC,id ASC` 确定保留项，其余设置retired_at、撤销授权，原配置不删除。既有迁移机制在写入前保存在线备份；UI清楚显示保留项和“历史停用配置”。
- 首次新配置使用稳定UUID。无ID重复保存相同初始表单更新有效记录；无ID不同配置或不同有效ID返回PROVIDER_EXISTS。显式编辑使用expected_revision做CAS。数据库约束防止绕过前端或并发创建。
- `GET /v0/generation-providers/retired` 返回保留历史，不返回密钥；`POST /v0/generation-providers/{id}/restore` 要求目标revision、active_id、active_revision同时匹配。先停用当前，再恢复目标；全部撤销外发授权、清除会话凭据，需要重新输入并启用。恢复与配置修改沿用生成worker互斥。
- Tauri `retired_generation_providers` / `restore_generation_provider` 与TS接口对应。启动/刷新/进入设置只读；设置默认编辑唯一记录，载入与保存时禁用表单，阻止重复提交。重启不保留API Key，不伪造已认证状态。

## 当前轮次展示与滚动

- 主对话只呈现问题、原有可发布答案正文、拒答/错误/处理中状态。原文摘录明确未生成答案。生成与支持性核验业务规则不变。
- 右侧`本次检索`只绑定当前answer_run.id，显示该轮冻结范围、真实PipelineDiagnostics、完整evidence/claim关系和核验状态。旧数据没有的诊断明确未记录，不推造；系统信息轮明确未检索、无论文引用。来源打开继续使用原有受控readSource和PDF SHA校验。
- 当前文献元数据题名与保存题名有差异时同时说明；版本用SHA显示，不把当前元数据冒充原轮快照。
- 提交即显示临时用户问题（没有伪造证据），只滚动聊天容器；收到稳定ID后替换。历史首次打开定位最后一轮；后续轮询/完成状态不触发滚动。更早页加载按高度差保持视口。新会话创建/载入期间输入与发送受控，避免点击被静默忽略。
- 主区/右栏各自限定高度并独立滚动；窄屏右栏移至下方的独立有界区域。
