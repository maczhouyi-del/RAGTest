# Contracts — 跨模块契约提案（尚未冻结）

这些文件是为了让 Codex 在多语言/多进程编程前对齐词汇和边界；**不代表 v1.1 已经审批过具体字段或已生成服务端实现**。

2026-10-24后续开发已实现部分端点/迁移；实际协议、Job投影、SourceAnchor与草案差异见[implementation-v0.1.md](implementation-v0.1.md)。原草案保留，不把未实现字段/能力当现有API。

按用户最新指令继续P1，项目/多对多关联/人工元数据/原件阅读和schema4的新增契约见[library-v0.1.md](library-v0.1.md)。P0原有子契约保留为其历史实现范围。

- `entity-dictionary.md`：领域数据实体、主键、引用一致性、向量与原始文献生命周期。
- `source-anchor.schema.json`：P0 可定位源文本的最小 JSON Schema（不对高亮准确性作保证）。
- `evidence-span.schema.json`：P3 预留 EvidenceSpan 结构，不能用它宣称 P0 已实现 Claim 核验。
- `job.schema.json`：SQLite Job/API 可观察数据结构；真实 DB migration 需另行实现。
- `sidecar.openapi.yaml`：P0 候选内部 API，**假定随机回环+token 路线**，仅供讨论；最终可能改用命名管道。Rust 可以中转授权，不可把此 API 直接暴露给任意浏览器。
- `vector-search-adapter.md`：sqlite-vec/LanceDB 相同语义的最小适配层规范。
- `query-and-coverage.md`：P2/P4 检索范围和覆盖逻辑不能相互替代。

## 审查时必须解决

1. 一页页码以 **1-based** 表示，PDF 元素/表格内部索引另行定义；不能混淆。
2. 坐标系仅为提议；旋转/CropBox、PDFium→PDF.js 实测之前，不得称为高精度定位。
3. `alignment_confidence` 是类别，**不是经金标校准的概率**。
4. JSON Schema 能检查字段形状，不能保证 `end > start`、PDF 哈希存在、SourceAnchor 真实可跳页；这些必须用数据库约束/业务检查/真实 PDF 测试。
5. API 的临时会话 token 应由 Rust 授权/注入、限本地进程；不放 JS 全局变量或磁盘日志。
6. 模型/解析指纹必须覆盖实质影响向量的权重、tokenizer/预处理和距离/归一化；不能只存字符串模型名。
7. FTS prefilter 和向量 exact KNN 必须遵守**正确的授权 scope**；不能先检索全库 topK 再过滤，因会漏掉授权范围内本应返回的最相关结果。

所有这些细节若与源 DOCX 不一致，优先使用 `specs/SOURCE_PRIORITY.md` 的冲突流程，产生 ADR。

连续P1–P4本地实现的新增子契约：

- [recovery-v0.2.md](recovery-v0.2.md)：批量导入/任务、目录授权、备份/恢复/工作区切换、文件版本归并/撤销、阅读批注与schema5–9。
- [search-v0.2.md](search-v0.2.md)：中英关键词、固定本地候选配置、索引世代、精确向量与RRF混合、范围过滤。
- [workbench-v0.2.md](workbench-v0.2.md)：实际Scope/Claim/Evidence、人机状态分离、逐篇Research检查点/修订/报告、生成worker与模型限制。

原草案不被覆盖。APIv0是当前开发子集，0.1.0握手仍兼容；health附加api_revision=0.2-local。P3/P4工程实现不等同原草案所有字段或科研质量已通过。

- [ocr-v0.2.md](ocr-v0.2.md)：显式离线OCR配置/重解析、资源限制、候选指纹与OCR页级来源质量。
- [history-lifecycle-v0.2.md](history-lifecycle-v0.2.md)：历史游标、选定计划按篇/观察分页、逐条模型指纹、手工撤稿/停用与导出时失效提示。

- [layout-tables-v0.2.md](layout-tables-v0.2.md)：已授权Docling离线候选、schema11表格/单元格与原文映射、分页核对/复核历史及证据引用；科学质量未验收。
