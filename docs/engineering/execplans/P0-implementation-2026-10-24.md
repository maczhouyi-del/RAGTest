# 全功能开发授权下的 P0 实施记录

2026-10-24 用户指令“继续开发全部功能”授权推进 P0—P5 功能开发，保留原安全/删除/模型下载/发布限制。当前目录继续使用 RAGSystem，无改名。旧记录中的未授权状态是上轮历史，不能当作本轮授权缺失；阶段门禁仍必须真实验证，不能由该指令推断已通过。

最初从P0-01/02本地部分和P0-08故障测试开始，现已按依赖推进P0-03—07局部实现与P0-09/10补测准备/审查；P0退出未获真实证据与人工复核前，不进入P1。用户后续已提供两台16GB设备信息和固定模型下载授权，模型已本地实测；Windows执行通道、人工金标、完整再分发审查仍缺。不标完整P0-00/P0-01或整体P0 PASS。

## 实现意图 文件与依赖

1. `engine/pyproject.toml`、`uv.lock`、`.python-version`：复用已装Python3.12.13；FastAPI/Uvicorn受限本地API，pytest/ruff/jsonschema和PyInstaller开发工具，确切版本由公开注册表核对后锁定。
2. `engine/ragsystem/{domain,ipc,storage,jobs,ingestion}/`：匿名stdin初始化/会话鉴权/随机回环/限额，SQLite WAL/FK/schema，持久Job租约fencing，SHA不可变原件和恢复；不实现P1身份智能合并。
3. `apps/desktop/`：固定版本React/TypeScript/Vite与Tauri2；Rust生命周期/受控IPC、单实例，前端固定健康/导入/任务操作；无通用Shell权限。
4. `packaging/`：本机Sidecar冻结与目标架构命名、Windows本地构建脚本/检查步骤；不宣称可从macOS生成已验收Windows包。
5. `tests/{unit,integration,desktop-e2e}/`：先状态机/鉴权/不可变文件失败用例，再实现；真实子进程、Unicode目录与合法PDF单独记录；合成PDF不算科研质量。
6. `contracts/`：保持0.1-draft已有端点，新增实现子契约说明启动握手/FileGrant/Job投影；本轮实现草案不等于ADR自动批准。
7. `.gitignore`、`rust-toolchain.toml`、`docs/legal/`、执行报告/PLANS/任务板：锁定版本、来源和测试证据；Rust仅项目`.tools/`，不改shell配置、不安装Skill/插件。

## 拟运行命令与验收

`uv sync --project engine`；`uv run --project engine python -m pytest -c engine/pyproject.toml`；`uv run --project engine ruff check engine tests tools`；`npm --prefix apps/desktop install`；`npm --prefix apps/desktop run typecheck`/`build`；项目Rust工具链的`cargo test/check --manifest-path apps/desktop/src-tauri/Cargo.toml --locked`；`uv run --project engine python packaging/build_sidecar.py`。实际命令、环境、stdout/stderr、退出码由`tools/run_logged.py`保存，失败记录保留。

验收：无凭据/旧凭据拒绝、无非回环监听、秘密不进UI/argv/log；进程退出回收；WAL/FK、幂等键冲突、过期worker不能发布；复制/发布/事务中断无覆盖和伪完成；迁移/备份恢复完整性可复现；真实PDF SHA与文件版本关系可查。Windows/科研质量独立BLOCKED，不用本机测试替代。

## 停止与后续

付费调用、模型下载、未授权Skill/插件、数据删除/迁移/对外发布不在本次常规自动执行范围。缺模型只完成不依赖它的持久化/适配协议，不伪造Embedding；缺Windows继续独立本地P0工作，保留安装门禁。任何原件覆盖/越权/无认证监听/重复发布先修复并复测，不扩大业务范围。
