# MVP 子契约 v0.3（兼容既有 0.1.0 进程握手）

依据 v1.1 §§2–4、6–7 与用户 MVP 任务；不更改主架构。旧 Research/审查、安全、任务、备份与原件代码保留。仅一级 UI 改为问答/文献/设置。原协议字段继续兼容，新增端点/可选字段如下。

## 导入和准备

原生对话框每批至多32个PDF，沿用逐文件授权、64MiB限制、SHA256原件不可变去重。导入任务完成后 UI 对版本ID去重，调用 `POST /v0/mvp/prepare`，body `{version_ids,idempotency_key}`。版本1..1000，禁止重复和无权/不可见版本。共用现有有界执行槽和 Jobs；父 verify 任务串联缺失解析及已配置索引更新。子解析/索引发布事务同时验证父子租约，父取消不会允许迟到发布。

未配置 E5 时仍可解析及关键词问答，准备任务返回 `mvp_preparation:needs_embedding_model`。已配置时更新当前候选后端；MVP设置入口优先sqlite-vec，LanceDB与同台基准保留在高级设置/工具中。单篇失败保存错误并继续其余篇，父任务最终 `PREPARATION_PARTIAL`。前端退出会丢失尚未提交的自动准备衔接；任务/原件持久，重新打开后“准备问答 / 更新索引”可补齐。没有宣称跨进程持久复合队列。

## 解析、词法与索引有效性

schema13 增量创建 `chunks_terms_v2`/`terms_indexed_chunks_v2`，旧FTS表不删除。FTS5 unicode61 + NFKC/casefold预处理；索引保留词频，中文单字及相邻二元词召回；查询去重，使用FTS5 BM25，RRF融合保持既有scope先过滤语义。旧库首次查询按当前可见Chunk补建词法投影。

新解析指纹为 pdfium-page-chunks-v2：每页400码点窗口、最多80码点重叠，偏好后半窗句末/换行边界。Chunk文本必须等于页清洗文本[start:end]，完整Chunk用于检索/证据。旧解析与页映射不自动改写。E5 512token溢出明确 `EMBEDDING_CONTEXT_LIMIT`，不再静默截断，overflow_policy纳入完整Embedding指纹；旧指纹空间保留，新规则首次构建可能需重算，之后同内容同指纹复用。某些罕见字符的400码点仍可能超512token，失败有据可查，不能声称任意文字均保证容纳。

发布索引保存受控相对路径和逐文件SHA256清单；不接受符号链接，发布前核对关联ID、可见内容指纹及租约。status校验文件清单，查询前后校验世代/内容/授权，缺损/陈旧拒绝向量检索，要求重建，不静默切换后端。旧索引无清单时标需重建，保留旧文件；已有匹配指纹向量可复用。此项是工程损坏检查，不是对拥有本机文件写权限攻击者的防篡改签名。

## GenerationProvider 与显式发送

结构接口 fingerprint / cancel_check / generate(task,data) / close。现有受监管本地 Qwen 与 OpenAI兼容 NetworkProvider 实现。切换生成模型不写active_index/embedding_records。schema14仅存 generation_providers 的id/name/kind/base_url/model/revision/updated_at，不存密钥。

- `GET /v0/generation-providers`：本地配置列表，configured仅表示当前会话具备调用条件，不代表已连通。
- `POST /v0/generation-providers`：`id|null,name,kind(api|magpie),base_url,model,expected_revision,api_key`，CAS更新，最多16项；不发网络请求。API密钥仅引擎会话内存，前端密码输入用后清空，不存localStorage/SQLite/日志。重启需重输；Magpie应用识别名不是订阅密钥。
- `POST /v0/generation-provider-probe`：临时`kind,base_url,api_key`，无需先保存/硬编码模型即可查模型目录。
- `POST /v0/generation-providers/{UUID}/probe`：显式获取模型目录；不发论文，不生成。
- `POST /v0/answers`兼容新增`provider_id|null,provider_revision|null,allow_external=false,per_paper_limit=3`。本地Qwen仍为null/local。网络生成必须明确true及所见配置revision完全匹配；冻结公开配置SHA到任务，执行前再次核对，变更则失败，不发送到新地址。UI每次发送后清除许可勾选。MVP显式设per_paper_limit=8，保留Top-8中同篇的相关片段，旧客户端默认每篇3；任务payload冻结该限制。无命中时零生成调用并拒答；不自动fallback、不自动调用付费服务。

远程API只允许HTTPS，本机HTTP可用；地址以/v1结尾，无userinfo/query/fragment、控制字符；禁用环境代理、重定向、自动重试。固定/models和/chat/completions，发送有界检索片段与问题，不上传PDF文件。响应JSON最多1MiB；连接/读超时30秒，有取消检查和响应处理时间限制。网络阻塞读取不能保证本地生成worker同等毫秒级取消。模型须支持Chat Completions的JSON对象响应；不兼容时显式失败，不悄悄换接口。

模型返回E1..En等临时编号，服务端只允许映射到本轮实际Chunk及精确原文，再复用既有来源/支持/可比性/人工核验字段。支持自检不确定时保留拒答；自检不是科学证据。外部服务模型版本无法独立核验，指纹明确 `server_model_version=not_independently_verified`。对话和模型草稿不进入检索证据库。

## 可选 Magpie

依据[官方集成文档](https://usemagpie.ai/docs/integrate)及[官方仓库文档](https://github.com/yetone/magpie/blob/main/docs/integrating.md)，2026-10-25核对。显式本机URL，默认http://127.0.0.1:3425/v1，可改端口；先GET/api/hello要求name=magpie及version，再GET/v1/models使用原始ID。Chat Completions携带应用标识Bearer magpie-ragsystem / User-Agent RAGSystem/0.1。仅访问本机地址；不读取或修改Magpie订阅凭据/配置，不安装网关/插件，不自动注册Agent。

Magpie可能按其设置路由到外部服务或执行其内部fallback，本应用不能据localhost断言纯本地。与API同样须逐请求确认所选网关/模型和发送范围；本应用不主动换Provider。关闭Magpie后可明确选择原文摘录、本地Qwen或其他已有连接。

## 验收边界

协议夹具不代表真实API/Magpie生成或人工金标。公开真实BERT/DPR、本地E5/Qwen、真实冻结程序与浏览器桥分别记录；浏览器桥不能替代原生对话框、Windows安装。没有人工金标时保持BLOCKED，不扩展1000篇容量验收。
