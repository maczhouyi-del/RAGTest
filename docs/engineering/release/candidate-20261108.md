# 2026-11-08 工程候选：构建、安装边界和恢复入口

这是BUILD_ONLY工程快照；正式发行NO-GO。源码功能验证、安装包生成、安装后原生可用和发行批准是四项不同结论。本轮只前两项有本机证据，完整状态见整改台账和同日工程报告。不推送、不上传安装包、不发布Release。

## 范围与资源

目标继续为Windows 11 x64与macOS Apple Silicon；本轮实际产物只有macOS ARM64、版本0.1.0。不支持以macOS构建替代Windows测试，不承诺Intel Mac/Linux或千篇性能。保留Tauri/Rust/React/Python/SQLite本地单用户架构，不加入后台服务、账户或自动更新。

| 层 | 当前候选内容 | 用户取得/联网边界 |
|---|---|---|
| 应用程序 | 文献/项目/对话、PDF阅读、来源核查、任务、备份/恢复 | 本地运行；不自动上传文献 |
| Python及动态推理运行时 | 冻结完整向量、ONNX、GGUF、OCR、Docling候选运行时 | 随本机工程包；目标逐组件NOTICE仍待审查 |
| Embedding | E5-small固定614241f622f53c4eeff9890bdc4f31cfecc418b3 | 权重不入包；设置页显式选择已取得、哈希匹配的目录；无资源可用关键词/摘录 |
| 可选本地生成 | Qwen GGUF固定91cad51170dc346986eccefdc2dd33a9da36ead9 | 权重不入包；不配置时不调用，本轮不下载新模型 |
| OCR | tessdata_fast固定65727574dfcd264acbb0c3e07860e4e9e9b22185 | 英/简中资源不入包，显式选择并校验 |
| 布局/表格 | Heron/TableFormer固定文件清单 | 资源不入包，实际版本/SHA/许可见docling-model-register.json |
| 远程模型 | 保留唯一API配置、会话凭据和按修订授权 | 只有用户显式配置授权才发送问题/有界上下文/片段；本轮只用loopback协议fixture，付费调用0 |

四份docs/legal/*model-register.json与产物清单记录模型版本和哈希；本轮未批准权重再分发。现有“选择资源目录”并不等于已形成普通用户可获取的资源包/可恢复下载GUI；REL-005仍阻塞。默认不自动下载、自动转云或伪报已就绪。

## 可重复的开发者构建

终端用户不需安装Python/Node/Rust；这些命令仅供构建者。使用仓库锁定开发环境，先运行审计/测试；下列BUILD_ONLY命令不豁免失败门禁，不安装或签名应用。

```sh
engine/.venv/bin/python packaging/build_sidecar.py \
  --build-label AUDIT-REMEDIATE-M2 \
  --include-vector-lab --include-generation-lab --include-ocr-lab --include-docling-lab \
  --output-directory .tools/build/<新的侧车目录> \
  --evidence-directory docs/engineering/evidence/AUDIT-REMEDIATE-20261108
engine/.venv/bin/python packaging/build_candidate.py \
  --sidecar-manifest <刚生成的sidecar时间戳.json> \
  --output-directory .tools/build/<新的候选目录>
```

入口先核对侧车/源码SHA、目标架构与完整运行时标志，使用全新目标目录，保留既有产物，beforeBuild使用`--emptyOutDir=false`。Mac明确`--no-sign`，不会调用签名/公证账户。构建不是字节级可重现性证明，时间戳/工具链需随清单保留。

Windows必须在x64构建机，额外提供`--webview2-manifest <清单.json>`：字段directory（相对清单路径的固定运行时目录）、version、files（每个相对路径至SHA256的映射，含msedgewebview2.exe）。文件集合/哈希完整一致、无符号链接才受理，使用fixedRuntime，不隐式下载latest bootstrapper。此分支只有合成准入测试；微软运行时取得/许可、原生DLL/VC运行时、NSIS非管理员离线安装未验证，REL-006保持阻塞。

## 已实际生成的本机产物

- app：`.tools/build/AUDIT-REMEDIATE-M2-candidate/target/aarch64-apple-darwin/release/bundle/macos/RAGSystem.app`。
- DMG：`.tools/build/AUDIT-REMEDIATE-M2-candidate/target/aarch64-apple-darwin/release/bundle/dmg/RAGSystem_0.1.0_aarch64.dmg`，458284217字节。
- DMG SHA256：`0e24cb88255d008354cc8695a3ada3c95c124350bba691800ce9de079427092f`。
- 内置侧车SHA256：`d37250dd83b982d3a97ba946e4d6d3f4bebcfc9948c4d466260c93a098a7b9cc`；本轮103项源码/锁/构建入口哈希一致，原件模型权重未入包。

hdiutil verify通过；只检查镜像完整性。codesign显示linker ad-hoc、无TeamIdentifier、Info.plist未绑定、无资源密封；不是Developer ID签名或公证。未执行Gatekeeper/干净安装认证，不提供绕过系统保护的安装命令。完整发布清单在candidate-20261108.json，本地原始构建清单在候选目录。

## 安装、数据与升级规则

发行验收时，Mac应在独立干净非管理员账户通过DMG复制到用户可用应用目录后启动；Windows应验证currentUser NSIS、中文/空格路径、离线固定WebView2和Defender。此为待执行步骤，本轮没有在现有用户账户启动同身份候选App，避免触及真实工作区。

应用文件、用户工作区与模型目录分别管理。卸载策略要求保留用户原件、SQLite、向量及外置模型；需要销毁时必须另获用户明确操作。本轮未验证Windows卸载器的实际行为，不将此要求冒充已实现的安装器保证。禁止将删除应用当作工作区清理或以覆盖旧数据测试升级。

本轮schema保持21，无历史迁移文件改变；复用scope_snapshots承载冻结准备范围。临时v20→21测试覆盖升级前快照、SQL失败回滚、备份副本重新升级；旧二进制遇到更高user_version拒绝。备份恢复仍写入新目录、核对清单/原件/索引，未完成任务或实际执行者尚在时拒绝切换；取消先隔离租约。真实安装升级、备份介质/大盘耗尽和卸载还需目标机测试。

恢复执行入口：先读AGENTS.md、PLANS.md、execplans/AUDIT-REMEDIATE-20261108.md、audit/remediation-status.md；核对独立分支与既有dirty文档，不reset/clean/stash。继续06目标SBOM/风险处置→17人工金标→REL-005用户资源取得→双平台干净安装链路。未获批准的非阻断项也没有自行延期。
