# MVP-02 第二轮功能开发

用户于 2026-10-25 明确授权 A→E 连续实施、每阶段独立本地 commit，禁止自动推送/发布。当前 main，工作树开工干净；不另建分支，不改写历史、不操作旧用户工作区。

## 范围与顺序

- A 键盘发送：MvpAsk.tsx、browser_smoke.cjs、browser_round2.cjs。Enter requestSubmit 共用校验，Shift/IME 不发送，同步防重复锁。
- B 会话：复用 conversations/answer_runs，增加最小版本化迁移与分页接口；workflows/history.py、workbench.py、generation_service.py、provider.py、IPC/Rust bridge/App/MvpAsk。历史有界、仅为上下文；重新检索原 PDF，保持引用验证。
- C Provider：GenerationConnections/MvpSettings/MvpAsk、provider_registry/network_provider 和迁移（必要时）。DeepSeek/OpenAI 预设地址，实际目录/手动 ID、显式无需认证；引擎会话秘密，状态分层；参数兼容明确报错，无自动云切换。协议文档只核对官方来源。
- D 元数据：复用 document_metadata，新增候选及来源版本化表，导入/解析恢复任务，本地规则提取、保守留空、人工优先，文献详情默认展示和显式编辑。
- E 全新工作区 2 篇许可公开 PDF + 现有 E5、持久化/重启、三轮、各轮 PDF、模型切换不重嵌入、元数据人工值保留、备份恢复。

## 不做

不优化检索相关性、章节/参考文献权重、Qwen 拒答或生成质量；不放松来源/模型支持校验，不新增大模型或外部服务。真实付费 API、真实论文外发未授权。无人工金标/Windows 访问，不扩大容量结论。

## 命令与证据

以现有配置为准：npm --prefix apps/desktop run build；engine/.venv/bin/python -m pytest；cargo test（项目工具链）；tools/browser_smoke.cjs（Playwright，模拟 Tauri 传输 + 真实引擎）；必要时本机原生 smoke/build。tools/run_logged.py 保存命令、平台、退出码和原始输出至 docs/engineering/evidence/MVP-02-2026-10-25/。

每阶段报告 MVP-02-{A..E}-2026-10-25.md，记录真实修改文件、失败及重测，不删除日志。阶段功能回归通过后提交本地 commit 继续；无法自动操作的原生 IME/Windows 等明确 NOT EXECUTED，不冒充 PASS。

## 状态

A/B/C/D/E 本地实现与自动化组合完成；原生完整操作/IME与正式平台/科研门禁待测，未宣称整体正式验收PASS。开工审查：已有 SHA 原件/解析/索引/引用/备份、SQLite v14、会话外键和生成协议；缺会话分页与连续 UI、有界上下文、Provider 分层状态、快捷键、自动元数据来源。

A 功能回归通过（build/browser exit0），首次 UI 就绪等待失败已保留并修复测试同步。原生中文 IME/Windows 未执行，见 A 报告；继续已授权 B。

B 功能回归 PASS：136 Python通过/12跳过，Rust3通过/3忽略，浏览器13条断言，v14迁移和会话重载通过。首轮Rust编译失败已修复，日志保留。继续C；冻结app和组合重启留E。

C 功能回归通过：Provider预设/模型目录/内存凭据草稿/分层状态/JSON参数兼容/授权协议测试通过，真实付费API未执行；详见C报告。继续D。

D 功能回归通过：自动书目候选/来源、人工优先、持久任务、重解析/去重/恢复测试通过；20条浏览器检查与布局复核。原生和质量门禁不冒充通过。继续E全新工作区组合验收。

E最终154 Python通过/7跳过，Rust3通过/3忽略，最终冻结组合39断言及原生启动通过；最终报告记录真实app、源码/二进制哈希、失败日志与人工待测。未push/publish。
