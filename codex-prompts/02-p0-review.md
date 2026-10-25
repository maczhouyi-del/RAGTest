# P0 审查指令：技术测试的独立证据整理

请作为代码审查与测试证据整理者审查目前的 RAGSystem 2.0 P0 实现，不要因本人之前编写了代码而默认认为实现正确。

阅读 `docs/phases/P0-acceptance.md` 全部 G01–G14 和 `docs/evaluation/` 的真实测试记录，逐项验证：

- 每条声称的 PASS 是否存在对应命令、退出码、数据集、硬件环境、实际安装器/二进制 SHA256、原始输出；不可复现时降为 NOT EXECUTED 或 BLOCKED。
- 真实 Windows 11、无 Docker/WSL/系统 Python/Node 安装是否完成；CI runner 不能替代真实用户安装。
- sqlite-vec 与 LanceDB 是否同样配置、同样 Embedding/过滤/Windows 路径、exact KNN；两边的失败与对账证据是否完整。
- 增量导入、新增 10 篇、重复文件、重启后是否真正复用了已存向量，是否报告了 EmbeddingSpace 指纹。
- PDF SourceAnchor 是否跨 DocumentVersion、页、bbox 和表格单元可核验，是否有错引与不可靠时退化机制。
- 备份和恢复是否涵盖 SQLite + PDF 原件 + 解析产物 + 外部向量及 Manifest；崩溃/磁盘满是否无静默丢失。
- IPC、凭据、数据外发、恶意 PDF、模型/解析器许可/哈希是否确实验证。
- 真实科研质量与工程性能是否分开汇报，P0 是否偷跑 P3/P4。

产生按 G01–G14 的 PASS/FAIL/BLOCKED/NOT EXECUTED、严重性、证据链接、需补测的最少步骤，以及 GO/NO-GO **建议**。你无权自行批准阶段放行或删除失败证据。
