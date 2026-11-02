# 正式发布门禁（HARDEN-01，未签字）

CI只验证源码，不发布或上传原始日志/论文。macOS与Windows开发runner不等于普通用户干净安装。GitHub workflow尚未在本轮运行（禁止commit/push）；本机源测试另有真实记录。CI固定公共action SHA、uv/Python/Node和仓库锁，不自动升级依赖，不使用任何用户Key。

1. 源码门禁：Python完整测试及跳过清单、Rust测试/Clippy、TS构建、契约/迁移/恢复/安全回归，无本轮引入FAIL。资源依赖项目另跑，跳过不算通过。
2. 依赖门禁：`uv lock --check --offline --project engine`、`uv pip check --python <项目python>`、`npm audit --package-lock-only --json`；`python tools/dependency_gate.py --output <本地目录> --online`生成源码锁SBOM与OSV记录。OSV仅发公开包名/版本，发现漏洞exit1、网络/响应阻塞exit2，不能当0漏洞。Cargo和Python漏洞若未获扫描结论仍P1；不盲目升级锁内所有包。
3. 许可门禁：源SBOM不是发行物料清单；每个实际Mach-O/PE/DLL和嵌入runtime需SHA、上游版权/NOTICE、实际许可证与再分发义务映射。PyInstaller bootloader exception、PDFium BUILD_LICENSES、Tesseract/Leptonica、Torch等逐目标审查；TableFormer逐权重许可证映射仍未完成。模型不随默认产物分发。负责人：发布工程/许可审查人。
4. 构建门禁：源编译、测试侧车、开发.app、正式安装包、签名/公证、干净安装分别记录。本轮只允许前两类（无正式发行包）。构建脚本不会证明发布权限；不得自动提交/推送/Release/上传用户内容。
5. 平台安全门禁：Windows11 x64普通账户/中文空格路径/Defender/WebView2/8GB与16GB、支持Mac版本/Intel、进程/权限/内存/磁盘异常矩阵。缺平台证据为BLOCKED。
6. 数据与科研门禁：原件不可变、幂等/迁移/取消/恢复，以及真实1000篇与人工金标分别评估。合成数据、模型自审和API200不能替代真实规模/人工科学判断。

若任意关键P1仍BLOCKED/FAIL，结论为暂不建议正式发布。建议负责人逐项签字与证据关联，Agent不替代发布批准。

## REMEDIATE-01 门禁更新

CI npm安装/构建/审计显式cwd=apps/desktop，npm ci仅在新CI工作区执行；本机不以npm ci清理现有node_modules。Python采用固定3.12.13 uv-managed独立构建，绕开已确认未编译扩展API的macOS Framework构建，并执行sqlite-vec真实加载预检；有向量功能的打包也必须预检。版本本身不能证明能力，正式包仍需逐平台实测。

OSV输出公开坐标、漏洞ID、affected范围/fixed版本/官方引用，生成dependency-summary.md并写入Actions Step Summary；部分详情失败保留已知发现，完整性不明exit2/BLOCKED。未知不能当无漏洞，无明细的历史FAIL不能当已处置。仅公共包信息允许外发，禁止原始用户日志/语料上传。

`python tools/binary_inventory.py --artifact <实际测试侧车> --output <新JSON> [--notice-map <逐文件审核映射>]`生成与二进制绑定的物料JSON与 `.cdx.json` 文件级SBOM。它不代替正式安装包SBOM、签名、公证、许可确认和干净安装；当前继续NO-GO。本轮报告见reports/REMEDIATE-01-2026-10-30.md。
