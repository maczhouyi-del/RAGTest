# RAGSystem 2.0 — 初步工程架构边界（P0 设计草案）

**状态：DRAFT，尚未 P0 实证。** 需求依据：v1.1 §2、§3、§4、§7、§8。

```text
┌─────────────────────────────────────────────────────────┐
│  Windows 11 x64 / Tauri 2 + React                        │
│  项目/文献最小界面、PDF.js Reader、诊断/任务反馈          │
└──────────────────────┬──────────────────────────────────┘
                       │ 受控 Tauri commands / 最小 IPC
┌──────────────────────▼──────────────────────────────────┐
│ Rust 壳：Sidecar 启停、单实例、文件授权、凭据与IPC身份验证 │
└──────────────────────┬──────────────────────────────────┘
                       │ Named Pipe 或 loopback + token（P0 比较）
┌──────────────────────▼──────────────────────────────────┐
│ Python Sidecar：可恢复 Job、Parse → Chunk → Embedding    │
│ Query / Evidence Source Anchor / VectorSearchAdapter    │
└──────────────────┬────────────────────┬─────────────────┘
                   │                    │
        SQLite WAL + FTS5         VectorSearchAdapter
       文献、版本、任务、            ├ sqlite-vec：候选 A
       Chunk、可见性和记录           └ LanceDB：候选 B
                   │
            不可变 PDF / ParseRun / 模型权重 / 报告文件
```

## 重要责任边界

- **Rust：** 创建 Sidecar、生命周期/权限/文件授权、IPC 身份验证、密钥及 UI-safe 响应；不直接决定科研结论。
- **Python：** 文献解析、增量索引、查询、任务持久化和后续证据工作流；PDF/OCR 内容绝无执行权限。
- **SQLite：** 所有可检索范围、DocumentVersion/Chunk/Job/发布状态的权威数据库。
- **向量后端：** 仅存取候选/精确 KNN 结果；结果必须与 SQLite 权威可见集合交集、校验并对账。
- **文件系统：** PDF 按内容哈希保存为不可变对象；解析中间产物保留配置/版本；备份 Manifest 校验。

## P0 最小纵向闭环

授权 PDF → SHA256 与 FileAsset 落盘 → ParseRun/page/Element → Chunk + SourceRegion → EmbeddingSpace/Record 持久化 → 适配层精确 KNN/基础 FTS → UI 显示检索引用 → 同一 doc_version/page/source region 回到 PDF → 关闭/恢复后不重新处理旧向量。

P0 的查询面板仅为验证检索和来源链接：**不宣称已实现 P3 的科研 Claim 论证/人工审查或 P4 的全集 Research。**

## 任务持久化与发布

1. 创建 Job 及幂等键并在短 SQLite 事务中提交；繁重计算事务外执行。
2. 写不可变衍生产物、向量候选；校验 SHA/维度/Chunk ID/可见性与已有重试。
3. 用 SQLite 短事务切换对应记录到 `READY` / `VISIBLE`（必要时登记待对账）；查询必须按 SQLite 已发布状态过滤。
4. 断电/Sidecar 崩溃后以 Job lease、心跳和对账恢复；重复执行不得重复发布或将旧版本混入结果。
5. LanceDB 模式不能假设 SQLite 与外部目录跨库原子事务；建立重试/对账策略、备份同步快照门禁。

## PDF 坐标映射设计候选

`SourceAnchor` 参见 `contracts/source-anchor.schema.json`。提供规范化的左上原点坐标与页面旋转/尺寸记录是**本包提出的候选契约**，必须在 P0 的带旋转、CropBox、双栏、表格 PDF 上对比 PDFium 与 PDF.js 进行实测。无法保证高亮正确则降级 page-only，并显示可靠度；不能生成臆造 bbox。

## P0 的升级解析

PDFium 快速提取 → 根据文字覆盖、顺序、乱码比例、表格及页级定位质量评分 → 对明确失败的页尝试 Docling/OCR（资源/许可/授权条件满足时）→ 保留 ParseRun、升级原因与逐页失败状态。触发阈值不在本包预填，应根据金标数据测量。

## 非目标与防扩张

- 首版不用 Docker、WSL、PostgreSQL、Redis、通用消息中间件、跨库 XA、默认 ANN 或多 Agent。
- 不内置大型生成 LLM 的安装资源；Embedding 必须本地可获得或明确阻塞；云调用必须受用户授权。
- 前端不直接访问用户任意磁盘路径；PDF 打开经 Rust 授权，Sidecar 不提供任意文件读取。
