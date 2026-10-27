# 正式发布门禁（HARDEN-01，未签字）

CI只验证源码，不发布或上传原始日志/论文。macOS与Windows开发runner不等于普通用户干净安装。GitHub workflow尚未在本轮运行（禁止commit/push）；本机源测试另有真实记录。CI固定公共action SHA、uv/Python/Node和仓库锁，不自动升级依赖，不使用任何用户Key。

1. 源码门禁：Python完整测试及跳过清单、Rust测试/Clippy、TS构建、契约/迁移/恢复/安全回归，无本轮引入FAIL。资源依赖项目另跑，跳过不算通过。
2. 依赖门禁：`uv lock --check --offline --project engine`、`uv pip check --python <项目python>`、`npm audit --package-lock-only --json`；`python tools/dependency_gate.py --output <本地目录> --online`生成源码锁SBOM与OSV记录。OSV仅发公开包名/版本，发现漏洞exit1、网络/响应阻塞exit2，不能当0漏洞。Cargo和Python漏洞若未获扫描结论仍P1；不盲目升级锁内所有包。
3. 许可门禁：源SBOM不是发行物料清单；每个实际Mach-O/PE/DLL和嵌入runtime需SHA、上游版权/NOTICE、实际许可证与再分发义务映射。PyInstaller bootloader exception、PDFium BUILD_LICENSES、Tesseract/Leptonica、Torch等逐目标审查；TableFormer逐权重许可证映射仍未完成。模型不随默认产物分发。负责人：发布工程/许可审查人。
4. 构建门禁：源编译、测试侧车、开发.app、正式安装包、签名/公证、干净安装分别记录。本轮只允许前两类（无正式发行包）。构建脚本不会证明发布权限；不得自动提交/推送/Release/上传用户内容。
5. 平台安全门禁：Windows11 x64普通账户/中文空格路径/Defender/WebView2/8GB与16GB、支持Mac版本/Intel、进程/权限/内存/磁盘异常矩阵。缺平台证据为BLOCKED。
6. 数据与科研门禁：原件不可变、幂等/迁移/取消/恢复，以及真实1000篇与人工金标分别评估。合成数据、模型自审和API200不能替代真实规模/人工科学判断。

若任意关键P1仍BLOCKED/FAIL，结论为暂不建议正式发布。建议负责人逐项签字与证据关联，Agent不替代发布批准。
