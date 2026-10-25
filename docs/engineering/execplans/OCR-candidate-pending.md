# OCR 候选接入（本地工程实现与回归完成，非最终选型）

用户明确批准 tessdata_fast 4.1.0 的 eng/chi_sim 与本项目内 Tesseract 候选依赖。实际 commit 65727574dfcd264acbb0c3e07860e4e9e9b22185 已由官方 annotated tag 解析，LICENSE Apache-2.0 已取得；两语言文件已逐一核对固定 Git blob、大小和 SHA256，清单见 docs/legal/ocr-model-register.json。旧连接失败保留在证据中，不再是授权阻塞。

需求：v1.1 §§3、4、7、9；在既有 PDFium 快路径/受监管 worker 中增加低文本页离线 OCR，不替换核心架构，不决定 Docling/最终OCR版本。tesserocr 2.12.0 作为可选 ocr-lab 项目依赖（官方PyPI带平台轮子）；安装、原生库再分发与Windows运行分别记录。

受影响：engine/pyproject.toml、uv.lock、parsing/ocr.py、worker.py、pipeline.py、ipc/server.py、directories.py、library/repository.py；Rust lib.rs/权限清单、bridge.ts/ModelSettings/文献诊断UI；packaging脚本；tests/integration/test_ocr.py、tools/experiment_local_ocr.py、contracts/ocr-v0.2.md、本轮报告/PLANS/合法资源登记。Research同时增加每条模型指纹与失败调用事件，避免恢复时混用来源。

流程：原生选目录→purpose=ocr一次授权→后台隔离probe/校验两个固定权重→存私有路径及公开指纹→显式选择OCR重解析。只有原生文本缺失/很少的页渲染灰度并识别；CPU、页数、像素、文本、输出和墙钟有界，取消/失租终止本任务子进程，不发布迟到结果。新解析短事务提交后才撤下旧Chunk。PDF原件哈希不改；OCR来源页级、未审查、无虚构bbox；低置信/失败页保持partial。

验收命令：run_logged + pytest OCR/Workbench回归、ruff、TS/Vite、Rust test/clippy、带OCR候选的冻结侧车与原生debug app、真实图像型PDF候选试验。试验从已许可BERT第一页本地栅格化生成，记录转换参数与原件SHA；其测试图像不是用户金标。工程PASS与OCR字符准确率/中文质量、Windows/干净安装/表格布局/人工科研验收独立。

证据：docs/engineering/evidence/continuous-2026-10-24/。必要测试失败先修复，未测标BLOCKED/NOT EXECUTED，不因用户连续开发指令宣称全部系统完成。不再重复请求同一候选授权。

实际结果：真实BERT图像型页、冻结包与Rust传输OCR通过；全量Python97PASS、Rust显式候选5PASS、完整浏览器链路及原生启动回收通过，具体边界/失败与产物hash见continuous报告。未将字符/中文/科研质量或Windows安装标PASS。
