# 本地证据与 Research 实现契约 v0.2

状态：本地开发实现子契约，增量扩展v0.1；不是P3/P4科研/平台验收通过。需求v1.1 §§4.5、6、7。保留既有`/v0`接口、0.1.0握手和SourceAnchor/EvidenceSpan草案字段；SQLite schema11向前迁移前保存快照，旧程序拒绝新schema。原始契约不改写为已批准标准。

## 范围与信任

`ScopeSnapshot`保存本轮项目、不可变PDF版本/SHA、题名、解析批次和解析状态；新解析不悄悄替换研究输入。项目ID和版本列表由当前SQLite可见性与项目关联校验。UI支持勾选范围；去重后的最多1000版本。全库/所有论文等明确完整性问题要求转Research，关键词路由是有界提示机制，不声称覆盖所有自然语言表达。

每轮问答重新检索当前授权原文；旧答案/人工笔记不是证据。会话ID用于持久分组，当前不自动把历史摘要作为检索上下文；含糊追问需用户在问题中说明。默认关键词；另有完整短语、精确向量和RRF混合。问答Top-K至多8片段，不承诺全库覆盖。

## 问答、引用和审查

`POST /v0/answers`：question、version_ids、project_id、mode(extractive|generative)、strategy、可选conversation_id。返回run/conversation/job ID，后台持久任务。`GET /v0/answers?project_id=UUID`仅取相同冻结项目的近30轮；省略代表未指定项目的全库范围会话。

摘录模式输出`evidence_only`，没有伪装成结论的Claim。生成模式仅可选已授权固定GGUF候选；模型从预先编号的原文片段中选择citation_id，provider在本地将其还原为确切chunk+quote；无模糊引文匹配、无自动改写引文。发布前重新验证引用属于本轮池、quote逐Unicode codepoint匹配、当前可见Chunk/Element/ParseRun/PDF SHA一致。任意伪造引用拒绝整轮发布，保留失败任务。Evidence包含符合原`evidence-span.schema.json`的`span`和页级SourceAnchor快照；坐标未校准，bbox不伪造。

Claim分别保存source_status、model_support、comparability、human_status，结果JSON保存条件/缺失限定项和支持审查理由、模型完整指纹。候选模型对Claim另行做supported/contradicted/uncertain检查，**模型自审不等同科研支持或人工确认**；无supported结果时拒答，仍保存草稿与审查状态。未知科学可比性保持not_assessed。模型输出纯文本/JSON渲染，不执行脚本、工具或PDF内指令。语义能力实际质量尚未验收。

`POST /v0/reviews/{claim_or_evidence_id}`：status(unreviewed|confirmed|rejected)、note；本地用户每次操作保留时间、备注和不可覆盖的记录快照，当前状态可改，历史不覆盖。原文重解析后旧引用保留历史但标stale_or_unavailable，不能继续当当前有效来源。

## Research与覆盖

`POST /v0/research`：问题、1–20个去重非空字段、版本范围、项目、模式；默认UI提供方法、数据集/人群、实验条件、样本量、指标、值、单位、划分、结果九类字段。先冻结计划，另行`POST /v0/research/{id}/run`运行。每个冻结版本有ResearchItem，逐可见Chunk扫描，不由Top-K代替；文献内片段进度与结果在同一短事务提交。

状态分别计数pending/running/completed/partial/needs_parse/failed/cancelled。completed表示完成该冻结解析批次且parse_status=ready，**不是人工确认全文科学理解**；partial解析不计完整覆盖。计划包含未解析PDF时标needs_parse；新解析需新建计划，不偷换快照。失败/取消后继续复用已提交Chunk检查点和Evidence ID，保留复核；已处理文献不重扫。

摘录候选只是关键词匹配的原文片段，每字段最多3条；value_origin=excerpt_candidate、meaning_status=evidence_insufficient。生成提取为model_draft，每条仍要求合法原文引用；数值或单位不因字符串出现就变成科学事实。原文含义reported/explicit_not_reported/evidence_insufficient、人工确认/否定、来源有效性、可比性独立。当前不提供自动单位换算、跨研究排名或“未提取即未报告”的推断。

`POST /v0/research/{plan}/observations/{evidence}`用expected_revision做CAS，人工可修改值、单位、实验行ID、含义、条件与可比性。条件支持方法、数据集、人群、样本量、指标、划分、实验条件。每次修改保留before/after/操作者/时间，恢复待审；原引文/位置不改写。不同实验可用不同记录/实验行标识，不默认合并实验。

`POST /v0/research/{id}/reports`保存不可变报告修订；包含冻结范围、处理状态、字段缺失、人工/来源/可比性状态、页码与来源ID。报告是生成时快照，导出前建议新修订。`GET /v0/reports/{id}`获取文本；Rust保存对话框仅创建工作区外的新文件，拒绝覆盖和符号链接。Markdown中的不可信内容按纯文本审阅，UI不渲染HTML。

## 本地模型、资源与恢复

生成配置仅由Rust目录选择→purpose=generator短期授权→固定文件名、revision/SHA校验；`POST /v0/generator`后台加载，取消/失租不得发布配置。`GET /v0/generator`不返回私有目录。权重不打入app，不自动联网下载；本地llama.cpp CPU4线程/context4096/temp0，保留runtime/版本/提示版本指纹，超过预算明确失败。每32输出token可检查取消；prefill/本地原生调用的最坏取消时延仍待测，不承诺强OS隔离。

单工作区独占进程锁后才允许立即隔离前驱租约；重启保留尝试/事件，Research检查点可续，失败问答须重新发起。测试的结构化Fixture只用于协议，不算真实模型或科学金标。

连续开发修正：范围冻结在同一个SQLite短事务内检查项目、可见版本、解析状态及批次并插入快照；模型处理后发布前再次检查项目范围。Research空白/扫描解析另标needs_ocr，单篇失败独立计数并继续其他文献。问答/研究列表是近30项，尚无完整历史分页；大计划/多报告的列表载荷优化与规模验收仍待做，不能由两篇样本推断千篇体验。

生成运行时实际已改为受监管子进程：固定`--generation-worker`、私有stdin/stdout，输入≤128KiB/输出≤256KiB，每次推理180秒超时；父进程以100ms轮询检查租约/取消，失败或取消只终止自己创建的worker。父死/EOF监护、worker异常退出与重建已做工程回归。标准错误保留在当前工作区data/model-worker-logs内，每个worker1MiB封顶并明确记录截断，前端不持路径。prompt v9对JSON字段/候选引用ID作有界grammar约束，简短输出由应用再核验。上下文按检索次序装入片段，超预算移除末尾片段并保存included/dropped ID；单片段仍超限则失败，不把未送入模型的内容冒充已审查。原文摘录完整性、模型支持和科学含义仍分别报告。

论文身份计数修正：新ScopeSnapshot同时冻结document_id。Research每篇逻辑论文只能明确选择一个PDF版本，重复论文版本返回DUPLICATE_PAPER_VERSIONS；UI切换同一论文的版本时替换旧勾选，并显示SHA前缀。冻结后人工归并导致身份变化时，继续运行前拒绝对应篇的旧身份；历史矩阵/新报告保留并显示范围身份警告，不能把旧计数当作当前去重后的论文数。原件/来源ID依旧不改写，旧快照未记录身份时保守提示重建。

后续增量：新版GUI使用history-lifecycle-v0.2中的列表元数据/单轮详情/单篇20条观察，不再每次轮询加载近30计划的全部观察和报告正文；旧端点保留兼容。OCR/停用/人工撤稿/解析或身份变化的来源警告独立呈现，旧报告body不改写，导出另附当前警告。Research每条模型观察与失败尝试保留模型/提示指纹。已批准同一Qwen新增可关闭的相关性复核策略，沿用私有worker与严格输入编号，不代表语义支持或科学比较通过。宽屏≥1600px支持范围/结果/原文三栏，较窄屏为证据抽屉；坐标未校准继续页级。

布局表格的增量端点、不可变行列/单元格来源与独立人工审查见[layout-tables-v0.2.md](layout-tables-v0.2.md)；不改变原EvidenceSpan形状或科学状态含义。
