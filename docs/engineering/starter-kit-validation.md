# 工程启动包自身校验记录（非产品验收）

- 生成日期：2026-10-24
- 检查范围：源 DOCX 完整复制、Markdown 与插图可读取、合同 JSON Schema 结构、Sidecar OpenAPI YAML 基本结构、P0 子任务 00–10、G01–G14、测试 CSV 表头/列数及 ZIP 文件成员/哈希。
- `tools/validate_kit.py` 的通过结果只意味着**规划文件和格式结构可解析**，不是任何应用功能 PASS。
- 未运行：Tauri/Sidecar、真实 Win11 安装、PDFium/Docling、Embedding、sqlite-vec/LanceDB 性能、备份/恢复、科研问题评测。
- 尚无真实论文 Gold Set / 模型权重 / 产品级性能数据；这些内容必须由 P0 在用户合法样本及实际设备上补充。

此文档区分“工程包静态质量检查”与“RAGSystem 2.0 实际发布门禁”，不得合并其状态。
