# MVP-01：极简本地PDF问答重构执行计划

用户要求：基于现有代码完成导入→保存→解析/Chunk→持久Embedding→BM25/向量RRF→生成→可信PDF引用，并同步RAGTest当前main。开头明确“当前main、无需新分支”优先于同一提示内的通用新分支条款；指定仓库源码推送已授权，付费API、真实科研论文/凭据外发、旧数据删除、安装包发布仍未授权。基线main 4ba13ddb0e719889237c62d715c063d74dd941c5，工作区干净。所有运行试验使用新工作区。

## 审查与复用

复用SHA原件发布/去重、SQLite短事务与迁移备份、任务租约/取消/恢复、页发布与原文偏移、E5完整指纹向量缓存、两后端精确向量基准/RRF、冻结范围与引文核验、备份恢复及Tauri文件授权。Research/复杂审查代码保留，不作为MVP一级入口。

确认缺口：旧App默认文献库且六个一级入口；导入/解析/索引操作割裂；关键词分词结果去重，丢失BM25词频，单字中文缺少独立召回；页内1200字符无重叠，中文可能超过E5的512token且默默截断；索引ready仅凭内容指纹/路径，缺少损坏与完整性检查；问答只有固定本地生成器，没有统一Provider/API配置；检索预览截至1000字符可能丢掉Chunk尾部上下文。旧工程测试不能替代人工检索金标。

## 实施顺序与文件

1. 保存本审查/方案、运行当前基线pytest并记录结果，提交方案。更新PLANS记录授权与分阶段状态。
2. 保留旧App为LegacyWorkspace，新App仅问答/文献/设置，新增MvpAsk/MvpLibrary/MvpSettings与所需样式。复用阅读器、文献详情及备份组件，高级项折叠。前端bridge、Rust固定命令、PythonMVP准备任务串联导入后的解析与索引；不得绕开授权/lease。
3. tokenizer/source_search新增版本化FTS迁移，不重写旧表；保存词频，补单字中文，查询去重。chunking保持精确子串、句子/换行边界与重叠，更新解析指纹；拒绝静默Embedding截断。hybrid/adapter校验发布世代、文件、ID和查询前后内容一致性；重建复用已有向量。优先验证sqlite-vec，LanceDB基准保留。
4. MVP问答冻结范围、逐引用验证、无来源拒答、PDF原文/证据显示；历史分页、按会话查看。端到端测试须实际导入/解析/E5持久化/混合检索/本地生成/PDF，不把模拟响应当模型质量通过。
5. GenerationProvider协议，复用隔离本地Qwen；新增显式用户配置的OpenAI兼容API。网络Provider仅用户选择且逐请求确认发送问题/检索片段；无自动外部fallback。密钥只在当前会话内存，不写SQLite/日志/localStorage，重启后重新输入。更换生成器不改Embedding/index配置。模型列表连接测试不带论文，不执行付费生成。
6. 上述本地核心工程闭环通过后才增加可选Magpie。依据https://usemagpie.ai/docs/integrate与yetone/magpie官方仓库integrating.md，显式本机地址、/api/hello、/v1/models、OpenAI兼容chat；不读取订阅凭据，不安装Magpie，不接管其路由。即使localhost网关也可能转发云，生成同样需用户确认。
7. 保留人工金标与1000篇容量门禁，前者未通过不得扩大容量验收。没有代表性人工标注时明确BLOCKED；工程夹具与公开PDF单独报告。

相关文件：apps/desktop/src与src-tauri固定IPC；engine/ragsystem/{models,workflows,ipc,parsing,chunking,retrieval,indexing,storage/migrations}；contracts增量、tests、tools真实试验和浏览器工具、README/PLANS及阶段报告。AGENTS/原设计/旧迁移不改。新增迁移前OnlineBackup，保留旧内容，不自动重解析用户库。

## 验证与验收

锁定venv pytest/Ruff、TS/Vite、cargo fmt/clippy/test；真实许可BERT/DPR与已有E5/Qwen资源，不增模型。新工作区真实HTTP端到端、进程重启复用、索引损坏/陈旧/缺项、中文与边界检索、生成器切换向量计数不变、无证据零调用/拒答、伪引用/取消/范围变化、备份与迁移、外部发送确认/重定向/秘密不落盘；API模拟服务只算协议测试。冻结源码前后SHA、实际冻结程序、浏览器桥与Mac原生测试分别记录。Windows/人工金标未执行不标PASS。证据只留本机docs/engineering/evidence/MVP-2026-10-25，阶段报告可随源码上传。

阶段结果逐步更新PLANS和docs/engineering/reports/MVP-2026-10-25.md；正常提交推送main，不强推、不发布Release。外部API真实生成因无端点/密钥/费用及数据范围授权保留NOT EXECUTED，不阻塞本地闭环和协议实现。
