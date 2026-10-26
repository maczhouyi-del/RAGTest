# MVP-03 授权、证据分流与分类设置（2026-10-26）

## 基线与授权

开工 main=39b13d7，工作树干净；公开基线 bd95619 之后的本地 MVP-02 保留。不查询/推送远端，不发布，不新增模型/依赖、不调用付费API或上传论文。用户仅授权以下 A/B/C，分别测试与本地提交，不改变科研支持性检查或检索排序。

## 实施顺序与范围

A Provider授权：SQLite v18新增非敏感修订绑定授权表；provider_registry/ipc mvp/Rust bridge/GenerationConnections/MvpAsk。保存并启用+独立开关；旧配置默认未授权，关键字段变更使旧授权失效；普通重输会话密钥保留同配置授权。NetworkProvider每次文献请求重新检查真实授权及配置，前端allow_external仅兼容字段，不能作为许可。密钥仍仅引擎内存。测试开关/并发撤销/配置更改/重启/不落盘/多轮模拟API。

B 最小意图与证据：workbench.py新增严格规则系统信息分支，读取真实选择/生成配置/Embedding，无检索、无LLM、无引用；普通问题保留原RAG/校验。系统问题允许空文献范围且不污染后续论文上下文。MvpAsk当前run找不到不退回旧run，新提交立即清右侧；历史仍保留。候选/获支持/无命中/失败/系统信息分开显示。测试拦截BM25/向量/生成调用、严格规则负例、浏览器慢请求/无命中/拒答/旧证据隔离。

C 分类设置：MvpSettings、ModelSettings、studio.css复用原组件，内部约200px导航+最大900px单内容区；模型服务/检索与索引/文献解析/工作区与数据/备份与恢复/高级与诊断。主导航与视觉保留，无新路由/UI库。切换分类重读已保存真实状态，不保留秘密输入。测试六分类互斥、模型/索引/备份/恢复、窄窗口无溢出。

## 验证与记录

macOS26.2 arm64/16GB；npm --prefix apps/desktop run build；engine/.venv/bin/python -m pytest -c engine/pyproject.toml；项目Rust cargo test；Chromium真实引擎+模拟Tauri桥。tools/run_logged.py记录原始命令/退出码/失败至 docs/engineering/evidence/MVP-03-2026-10-26/。按需求更新跨进程增量契约，旧接口保留兼容，数据库升级前快照与事务保护不变。

不把模拟API当真实厂商，不把浏览器桥当原生文件对话框/Windows，不把支持性fixture当科学质量。最终必要时重建冻结引擎与本地开发app（保留旧产物），做原生启动回收；原生完整交互未测则明确标记。

## 状态

A/B/C IMPLEMENTED AND TESTED（本机工程功能；正式平台/科研门禁不变）。审查已确认旧逐轮consent、所有run默认检索、selectedId缺失时退回最后答案、设置纵向堆叠均存在。

A实现/定向及浏览器回归通过；sqlite.Row与异步开关问题已修复，失败日志保留；详见A报告。B开始。

B系统信息/证据隔离及28条真实引擎浏览器检查通过，全文回归163 PASS/12 SKIP；见B报告，C开始。

C六分类与最终冻结组合78检查、全Python163 PASS/12 SKIP、Rust复测3 PASS/3 ignored、Mac原生启动回收通过；初次并发冻结启动失败保留，见C报告与组合验收。当前用户任务已完成，停止，不push或推进质量优化。
