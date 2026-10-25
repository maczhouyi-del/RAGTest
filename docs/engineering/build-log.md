# 构建和测试日志索引

## 首轮规划包历史事实（2026-10-24；后续开发见文末）

- 已创建本 Codex 规划包（文本草案、接口 Schema、验收矩阵、提示词）。
- **尚未执行 P0 代码实现、Windows 安装、PDF 解析、数据库/向量后端 Benchmark、模型质量评测。**
- 本包格式校验若通过，**仅代表文件结构/Schema 可解析**，不是产品 PASS。

## 后续记录格式

| 日期 | Task ID | commit | 平台 | 测试类别 | 状态 | 原始日志/结果路径 | 人工确认 |
|---|---|---|---|---|---|---|---|
| 待填 | P0-xx | 待填 | 待填 | 待填 | NOT EXECUTED | 待填 | 待填 |

## 2026-10-24 P0-00 本地审查

| 日期 | Task ID | commit | 平台 | 测试类别 | 状态 | 原始日志/结果路径 | 人工确认 |
|---|---|---|---|---|---|---|---|
| 2026-10-24 | P0-00 | 无Git仓库 | macOS26.2 arm64/Python3.9.6 | 启动包结构校验 | PASS（限定范围；jsonschema缺失warning） | `evidence/P0-00-2026-10-24/commands.json`、`final-checks.json` | 待审阅 |
| 2026-10-24 | P0-00 | 同上 | 同上 | 原始Manifest/源文核对 | Manifest FAIL：缺.gitignore；36项匹配；DOCX/两图一致 | `evidence/P0-00-2026-10-24/baseline-manifest-check.json`、`source-integrity.json`、`source-text-coverage.json` | 待审阅 |
| 2026-10-24 | P0-00 | 同上 | 当前未提供Win11/金标 | Windows/科研质量 | BLOCKED；应用功能NOT EXECUTED | `reports/P0-00-2026-10-24.md` | 未批准后续实施 |

本轮只生成计划/报告/ADR和证据，未构建应用或安装包。后续任务与全部产品Gate没有PASS证据；完整P0-00资源准入尚未完成。变更清单见`evidence/P0-00-2026-10-24/change-summary.json`。

## 后续开发执行

用户已授权继续开发。当前Mac Python42测试、Rust2测试、clippy、TypeScript/Vite、Tauri debug `.app`构建通过；原生WebView→Rust→冻结Sidecar启动/父进程终止回收通过，浏览器UI真实解析/FTS/PDF渲染通过但传输层模拟。两篇真实PDF/固定批准模型/候选向量A/B已执行。Windows原生构建与干净安装、人工科研金标未执行。

完整命令/平台/退出码/原始输出在`evidence/P0-implementation-2026-10-24/commands-index.json`及同目录时间戳JSON中；失败日志保留。当前结果边界、恢复方法、剩余门禁见[本轮实施报告](reports/P0-implementation-2026-10-24.md)。整体P0仍BLOCKED，未进入P1，不以本节局部PASS代替阶段批准。

## 最新P1-01开发（上述P0段落为历史）

用户要求标记延期非阻断测试后继续功能，按ADR-009继续独立P1，P0验收未通过。项目/人工元数据/未解析PDF阅读/项目范围检索已实现，本机49个Python回归通过、1个未变更模型用例SKIP，Rust3通过，TS/Tauri app与浏览器真实引擎/原生启动回收通过。详细记录和未执行项见[P1-01报告](reports/P1-01-2026-10-24.md)，原始日志`evidence/P1-01-2026-10-24/`。没有重跑千篇/Windows/科研评测来阻断本轮开发，没有把延期项改为PASS。
