# v1.1 → Codex 工程产物追踪表

此表只追踪来源，不将工作包中的细化实现细节伪称原方案中已有。

| v1.1 原文位置 | 规定的产品/技术原则 | 对应工程文件 |
|---|---|---|
| §§1.1–1.5 | 单用户、约 1000 篇、可核查答案、研究完整性和不可信输入 | `README.md`, `AGENTS.md`, `docs/security/security-baseline.md` |
| §§2.1–2.4 | Tauri/React/Rust/Python 分工、受控 IPC、干净 Windows | `docs/architecture/architecture-v0.md`, `P0-taskboard.md` P0-01 |
| §§3.1–3.2 | Embedding 与索引分离、内容指纹、常规增量和 IndexGeneration | `contracts/entity-dictionary.md`, `contracts/vector-search-adapter.md`, P0-05 |
| §§3.3–3.6 | SQLite 权威、sqlite-vec/LanceDB 候选、备份与选型 | `P0-benchmark.md`, P0-06/08, ADR 模板 |
| §§4.1–4.2 | PDFium/Docling/OCR 质量路由、Chunk 与 SourceRegion 映射 | P0-03/04、`contracts/source-anchor.schema.json` |
| §§4.3–4.5 | 中文 FTS5、混合检索、局部问答 vs 全集研究 | `PLANS.md` P2/P4、`contracts/query-and-coverage.md` |
| §§5.1–5.5 | 项目/文献/问答/深入研究 UI，证据三栏 | P0-07 最小原型；P1/P3/P4 后续 |
| §§6.1–6.5 | Claim/Evidence 三层状态、人工复核、覆盖/缺失边界 | `contracts/evidence-span.schema.json`, `contracts/query-and-coverage.md`（P3/P4 预留） |
| §§7.1–7.3 | Job/lease/幂等/取消/恢复 | `contracts/job.schema.json`, `contracts/entity-dictionary.md`, P0-02/08 |
| §§8.1–8.6 | 安装/首次引导/隐私/迁移/签名/恶意 PDF | `docs/security/security-baseline.md`, P0-01/08/09 |
| §§9.1–9.5 | 测试类别、30–50/100–200/1000 篇评测、性能预算 | `P0-acceptance.md`, `P0-benchmark.md`, `docs/evaluation/` |
| §§10.1–10.4 | P0–P5 路线、风险、目录和首阶段任务 | `PLANS.md`, `P0-taskboard.md`, `docs/engineering/open-decisions.md` |
| §11 | 借鉴的开源项目、许可证与再分发 | `AGENTS.md`, `docs/security/security-baseline.md` |
| 附录 A | 容量与性能仍未决定、源与人工审查的重要性 | `PLANS.md`, `P0-acceptance.md`, `open-decisions.md` |

**非来源决策：** 本包提出的 API 路径/字段、详细任务 ID、JSON Schema 字段细节、测试模板和部分安全操作细则，是落实原方案的**建议**，需 Codex 校对并经项目负责人批准，不能在审计中引用成已确认事实。
