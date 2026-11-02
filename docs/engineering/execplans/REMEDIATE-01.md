# REMEDIATE-01 — 用户全面整改清单（2026-10-29）

授权：本轮附件要求依次实施 P1-01/02/03/04/07/05/06、P2-08/09/10/11，最后完整回归。这里的编号属于整改清单，不覆盖历史 P1 文献基础任务编号。未通过的外部验收保留 BLOCKED，继续独立可执行工作；不提交、推送、发布、下载模型或触碰旧数据。

基线：main / 1282b1066523d4a1d0a8ce0c34df8715db09201b，初始 git status --short 为空。

## 实施及文件范围（实施前登记）

1. P1-01：vector_adapters/sqlite_vec.py、retrieval/hybrid.py、前端后端选择、vector contract tests、CI。验证实际 Python/SQLite 扩展能力，支持时真实距离/持久化测试，不支持时失败关闭。保持 SQLite 权威和现有后端候选架构。
2. P1-02：.github/workflows/ci.yml、release gate tests。npm 明确 cwd 与 npm ci，锁文件不漂移。
3. P1-03：tools/dependency_gate.py、release gate tests、发布门禁。OSV 公共坐标/详情/日志/分诊，未知失败关闭；确认可修复依赖才改锁。
4. P1-04：parsing/process.py、limits.py、隔离模块和测试、安全基线。资源/生命周期增量，不将普通进程称沙箱；目标平台权限和网络缺口继续阻断。
5. P1-07：models/provider.py、local_generator.py、network_provider.py、workflows/workbench.py、相关测试。强制实际输入审计、截取及来源指纹，无候选池降级。
6. P1-05：评测工具/测试/goldset-protocol；检查合法本地数据和预先批准阈值，缺失时不计算虚假科学指标。
7. P1-06：packaging、物料工具/测试、NOTICE、README、release-gates。实际二进制清单与源码锁分开，签名/许可/干净安装缺口保留。
8. P2-08：统一生成输出契约/硬上限及相关测试；P2-09：reranking.py 与测试，禁止跨批直接比较原始分数，默认关闭。
9. P2-10：metadata_scope.py/hybrid.py/server.py/workbench.py/前端与契约、回归测试，授权内筛选与冻结范围检查分离。
10. P2-11：library/repository.py/workbench.py/MvpAsk.tsx/来源卡片、版本测试；默认最近导入版本及显式版本选择，保持来源和撤回保护。

## 验证与风险

每项针对 pytest，受影响模块回归，最终执行实际配置的 Ruff、pytest、npm build、cargo test/clippy、uv lock/check、OSV/npm audit、现有评测与诊断。命令用 tools/run_logged.py 留存 argv/平台/时间/退出码于 docs/engineering/evidence/REMEDIATE-01/；报告及 PLANS 更新。本机 macOS arm64，不冒充 Windows 或干净安装。恶意 PDF 使用安全合成边界测试，不执行真实 exploit。无人工批准阈值、合法千篇语料、签名环境时对应完整验收 BLOCKED。
