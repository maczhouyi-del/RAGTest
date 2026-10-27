# RAG-01：检索到回答核心链路（2026-10-27）

用户本轮附件批准阶段0–8连续实施，最新消息批准本地修改后同步指定RAGTest；覆盖旧任务的禁止推送记录。基线main/12cb91f，工作区干净。保留现有技术、数据、模型及所有正式验收门禁；不下载、不调用真实API、不发布安装包。

## 范围与验收

1. 确定性系统问法共用引擎清单；空库也可读真实配置，检索/推理/外部调用均0；复合问题保留两部分。
2. 保留SQLite范围、解析批次、项目和索引世代检查；审查FTS、E5前缀/溢出/复用，词法与向量各召回50再融合。
3. RRF保留原始通道排名、确定性破同分；重复向量保留来源，减少同内容挤占；局部问答最多8、默认每逻辑论文3。
4. 独立当前问题优先，明确指代才用最近上下文；持久记录实际查询。区分no_hits/insufficient_evidence/generation_failed，保留原数据库状态及引用验证。
5. 可选模型复核仍默认关闭；离线同范围策略评估、金标模板、质量缺口登记，不制造人工分数。

## 拟修改文件和依赖

`engine/ragsystem/workflows/{system_information,workbench}.py`、`retrieval/{hybrid,source_search,evaluation}.py`、`models/{provider,local_generator,network_provider,generation_service}.py`（共享冲突处理提示与向后兼容指纹）、`apps/desktop/src/{bridge.ts,components/MvpAsk.tsx}`、相关unit/integration测试、`tools/`评估工具、`contracts/`增量子契约、`docs/evaluation/`、PLANS/延期登记/工程报告。无新增依赖、无schema迁移。

## 顺序与命令

基线pytest → 路由失败用例/实现/复测 → RRF与配额失败用例/修复/复测 → 查询上下文/引用/状态测试及修复 → 离线评估工具验证 → 完整pytest、ruff、npm build、cargo test --locked、可运行浏览器回归。所有命令用`tools/run_logged.py`保存至`docs/engineering/evidence/RAG-01-2026-10-27/`，退出码/平台/时间逐项记载。只使用既有venv、工具链及已批准本地资源，临时工作区与真实用户库隔离。

## 风险与门禁

中文OR扩展召回噪声需金标衡量，不主观宣称精度提升。原始向量排名与展示排名区分；同内容来源不能删除。历史结果向后兼容。引用真实性只能确定性验证原文，模型支持检查不能替代独立科学或人工审查。无Windows机器、真实1000篇或双人裁定金标时分别BLOCKED，继续其他独立任务；最终发布NO-GO。

## 实际结果

范围已实现并完成工程回归。首次失败、修复与最终命令/计数见[RAG-01报告](../reports/RAG-01-2026-10-27.md)和版本化验证清单；原始输出、截图、隔离快照及冻结构建清单保留本机evidence，不纳入源码上传。真实科研、千篇容量和Windows正式验收没有自动通过。
