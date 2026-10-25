# 批准后的 Codex 指令：只执行已批准的 P0 子任务

已批准开始实施 RAGSystem 2.0 **P0 当前子任务**，但没有批准 P1–P5、上线、远端推送或主架构重设计。

请先核对工作树与 `AGENTS.md`、`PLANS.md`、`docs/phases/P0-taskboard.md`、`docs/phases/P0-acceptance.md`、`contracts/`，只在批准的任务 ID 范围执行（本轮任务 ID 和授权文件范围以我紧接着的消息为准）。

强制工作流程：

1. 读取相关 v1.1 节号与合同草案，检查有没有未批准的设计变更；遇到变化先起 ADR 提案。
2. 列出本轮受影响文件及不可逆操作风险，再开始实现。保持功能闭环可运行；禁止空 UI 假数据骗过验收。
3. 先编写基本失败/边界/错误用例，再补实现；在 Python、Rust、React 间保持版本化契约一致。
4. 本轮覆盖至少一个真实 PDF 或真实 Windows 路径的最小独立测试（环境缺失要明确 BLOCKED/NOT EXECUTED，不得生成假 PASS）。
5. 保留执行过的命令、环境、退出码、日志摘要、编译/安装产物指纹；测试失败则在范围内自主修复、重跑。
6. 检查恢复、权限、错误处理及来源坐标降级的实际行为。
7. 完成后生成一份 `docs/engineering/phase-report-template.md` 格式的实际任务报告，并更新 `PLANS.md` 与 `docs/engineering/build-log.md`。

输出只报告已验证的完成项、测试边界、失败项、数据与安全风险和下一轮的最小任务。不要在 P0 验收前宣称系统已达到 1000 篇性能、引用语义正确性或单 EXE 发行标准。
