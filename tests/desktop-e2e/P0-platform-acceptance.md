# P0 原生平台人工验收（尚未执行）

Windows构建机与干净验收环境分开记录；用户现有Windows电脑和Mac均16GB，不自动满足8GB档。当前只有Mac开发机测试，不存在Windows PASS。

## Windows 构建

在Windows11x64构建机准备Python3.12可用的uv、Node22、Rust1.99.1 MSVC工具链、VS C++/Windows SDK、PowerShell7。无需Docker/WSL。使用同一份本地工程，避开Mac的`.tools`、`.venv`、`node_modules`、`target`二进制，不复制用户资料。目录含空格/中文。执行：

```powershell
Start-Transcript -Path (Join-Path $PWD ("windows-build-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ") + ".log"))
pwsh -File packaging/build-windows.ps1
$BuildExit = $LASTEXITCODE
Stop-Transcript
$BuildExit
```

构建脚本**未在Windows执行**。默认不下载模型；模型测试没有显式本地路径则SKIP，不能写PASS。若准备已批准同revision资源，先验证manifest，再设置`RAGSYSTEM_MODEL_DIR`。构建产物在Tauri `target/x86_64-pc-windows-msvc/release/bundle/nsis/`，实际名称以输出为准。记录安装器和sidecar SHA。网络仅开发依赖下载，不允许上传源码/PDF。

## 干净系统验收

复制安装器到无Python/Node/Rust/Docker/WSL的普通账户Windows11x64环境，记录OS build、CPU/RAM、Defender/WebView2版本；分别记录16GB与8GB条件。不要为通过而安装开发工具。

| Case | 操作/通过条件 | 状态/证据 |
|---|---|---|
| W01 | 普通账户，中文用户名、中文/空格安装/数据路径；安装和启动无系统Python | NOT EXECUTED |
| W02 | 再开一次只出现一个窗口/一个主sidecar；授权健康成功 | NOT EXECUTED |
| W03 | 导入manifest内两篇PDF、重复导入、解析、退出重启；SHA/任务/文献持久 | NOT EXECUTED |
| W04 | 关键词BERT检索→打开来源；核对版本/页数/页级提示，扫描失败不冒充成功 | NOT EXECUTED |
| W05 | 无token/旧token、浏览器Origin拒绝；只监听127.0.0.1；UI/argv/日志不含会话token | NOT EXECUTED |
| W06 | 解析中退出、强制结束sidecar、重新启动；任务有状态且无孤儿命中，子进程结束 | NOT EXECUTED |
| W07 | 恢复到全新目录，核对PDF/SQLite/向量manifest；不覆盖原库 | NOT EXECUTED |
| W08 | 非管理员权限、Defender干预/WebView2缺失和磁盘满错误明确可见 | NOT EXECUTED |
| W09 | 卸载保留资料；此操作只对新测试安装且由操作者明确执行，不清理旧项目 | NOT EXECUTED |

可在启动和退出后分别运行`pwsh -File tools/collect-windows-evidence.ps1 -InstallerPath '<安装器绝对路径>'`，只写本地环境/进程/监听摘要，无上传。收集脚本需要PowerShell7，但不是应用运行依赖；可由测试人员离线收集。环境快照本身不判定用例PASS。

## macOS

Apple Silicon当前构建：`sh packaging/build-macos.sh`（需已有项目Rust与npm依赖）。默认debug `.app`仅供本地开发，不代表签名、公证或Gatekeeper验收。低于当前26.2的macOS、Intel、干净Mac、非管理员与中文目录、离线安装、单实例、强制退出和恢复逐项同上记录。配置minimumSystemVersion15.5只是当前打包下限，最低版本兼容性待实测。

原生GUI步骤、文件选择器、WebView权限和安装行为不能由模拟Tauri桥的浏览器测试替代。完成者填实际时间/平台/版本/退出码/截图/日志，不删除失败记录；交项目负责人审查G01—G14后才有阶段结论。
