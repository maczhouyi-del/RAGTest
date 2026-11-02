# CODE-CLEANUP 执行计划

用户2026-11-02附件授权全仓审查、等价清理、测试及独立分支/PR；不直推main，不改算法/契约/schema，不动用户数据，不调用付费API。基线c3b6d8a，工作区干净，分支codex/code-cleanup-20261102。

先实跑Python353项基线、TS/Vite、Rust含候选及Clippy/Ruff。建立文件/import/IPC注册图，人工追踪主要流程；按A核心/B兼容/C可删除/D重复/E不确定分类。只实施证据充分的局部重构，优先Rust三个模型目录选择器、前端证据重复解析、History分页投影；不同安全语义不强行合并。LegacyWorkspace受ADR-010保留约束，不删除隐藏Research或动态注册函数；CSS无法证明无用时保留。

预期文件为lib.rs、TurnEvidence.tsx、history.py、相邻回归测试与报告。不增加依赖/迁移。安全风险是目录选择跨工作区竞态、游标顺序/项目隔离、坏历史anchor降级；保留校验顺序、事务与返回字段并针对测试。完成后重新冻结侧车，完整前后测试，真实PDF/E5浏览器回归；Windows/人工金标未执行单列。报告按用户A–G格式，逻辑拆分Conventional Commits，推送清理分支并创建main PR，不合并。

用户后续明确调整：本地修改验证完成后直接提交并推送main，不创建PR。该最新指令覆盖本计划及附件的分支/PR交付条款；仍不强推、不改算法、不上传数据。开发分支仅用于隔离实施，最终快进到main。
