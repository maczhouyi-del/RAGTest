# 本地依赖、模型与样本许可登记（DRAFT）

`dependency-inventory-*.json`由`tools/dependency_inventory.py`读取实际Python安装元数据、npm lock和Cargo lock生成，含版本、来源/完整性和本地可见许可文本SHA。`license-texts/`保留这些文本原件；缺少本地源包的其他平台依赖明确标缺，不据包名推断许可。此清单包含开发/实验依赖，不等同安装包精确SBOM，也不是已完成的法律审查。

Python源/二进制固定于`engine/uv.lock`，当前通过清华公开PyPI镜像取包，hash来自锁；Rust官方端点TLS失败后使用RsProxy下载项目内工具链并校验，首次镜像信任与Windows DLL审查仍待补。Node固定`package-lock.json`；Rust固定`Cargo.lock`。不使用系统Python作为终端用户依赖。

| 资源 | 已保留依据 | 再分发范围/剩余工作 |
|---|---|---|
| pypdfium2 5.14.0 + PDFium 156.0.8076.0 | wheel内Apache/BSD/CC声明及`data/darwin_arm64/BUILD_LICENSES` | 多个上游组件许可，不能只贴包装器单项；Windows对应二进制NOTICE待实际构建核对 |
| PyInstaller 6.22.3 | 原文COPYING/bootloader exception | 本地冻结不等于应用必须GPL；分发仍按原文判断修改及其他组件义务，未作法律裁定 |
| PDF.js 6.4.299 | npm包license/NOTICE | 打包时保留所需版权/NOTICE，待产物审计 |
| React19.3.1、Tauri2.12.4、FastAPI0.162.0等 | 实际元数据及license-texts | 全部传递依赖见inventory，未完成Windows运行时审计/发行批准 |
| intfloat/multilingual-e5-small | 官方模型卡声明MIT；固定revision及全部下载文件SHA见模型登记 | 仅已授权的本地候选试验；模型未随默认app打包。模型卡声明不自动解决训练数据或未来发布权利问题 |
| BERT/DPR两篇测试论文 | 作者/题目/来源、CC-BY4.0依据、SHA见样本manifest与NOTICES | 未修改原PDF；保留署名与许可链接，仅工程试验，没有人工金标 |

安装包的实际二进制依赖、Apple/Windows运行时、全部版权署名、上游数据/模型限制、签名/发行条件尚未完整核对，G13保持BLOCKED，不发布。

2026-10-24连续开发补充：用户明确批准Qwen/Qwen2.5-1.5B-Instruct-GGUF固定revision `91cad51170dc346986eccefdc2dd33a9da36ead9`、`qwen2.5-1.5b-instruct-q4_k_m.gguf`（1,117,320,736字节，SHA256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`）与本项目本地推理依赖。首次官方TLS失败保留；重试经hf-mirror.com重定向至官方Hugging Face/CDN，固定SHA校验通过。固定revision README与完整Apache-2.0 LICENSE在`models/Qwen2.5-1.5B-Instruct-GGUF/`，原始源和hash见continuous证据的generator-license-sources.json。仅本机候选试验，权重不进入app。

本项目venv新增llama-cpp-python0.3.36（构建vendored llama.cpp/ggml）、diskcache5.6.3、Jinja2 3.1.6、MarkupSafe3.0.4，精确包/源/hash在uv.lock。`dependency-inventory-20261024T091852502540Z.json`更新为63个已装Python分发、93项npm锁、458项Cargo锁；包含开发与目标平台缺失条目，不代表完整二进制SBOM。新增依赖可见许可原文已保留，完整动态库/系统框架/Windows再分发审查仍BLOCKED。

OCR后续明确授权：tessdata_fast固定commit、两语言数据Git blob/大小/SHA和完整Apache-2.0 LICENSE在ocr-model-register.json及models/tessdata-fast-*/LICENSE；tesserocr2.12.0来自官方PyPI显式索引，uv.lock保留Mac/Windows轮子hash。此后inventory `dependency-inventory-20261024T134606313494Z.json`为64项Python/93npm/458Cargo。Mac轮子标签macosx_15_0_arm64，观察到Tesseract5.5.3/Leptonica1.87.0，实际11个原生二进制hash及链接关系在ocr-native-inventory-macos.json；绑定的MIT文本不能替代所有原生组件条款，完整发行审查继续BLOCKED。用户随后明确授权Docling两个候选及项目内依赖；固定资源/镜像来源说明、SHA/大小/小文件Git blob和模型卡见docling-model-register.json。Docling-slim2.142.1/docling-core2.104.0/docling-ibm-models4.0.4、Torch2.14.1/torchvision0.29.1/Transformers5.20.2/OpenCV-headless4.14.0.94等已锁入docling-lab。最新dependency-inventory-20261024T150911846052Z.json为96项Python/93npm/458Cargo，包含新增许可原文。Heron模型卡Apache-2.0，docling-models仓库卡CDLA-Permissive-2.0/Apache-2.0，但没有逐文件映射，不能直接断言TableFormer单权重的最终再分发许可；官方CDLA原文HTML与模型卡保留于models/docling-candidates/，再分发审查继续BLOCKED。

HARDEN-01补充：tools/dependency_gate.py生成CycloneDX1.6格式的**源码锁库存**，包含全部公开锁依赖及已安装Python许可声明，未安装或目标原生组件明确未审；不是发行二进制SBOM或法律批准。OSV需要显式--online，发送公开依赖坐标，网络失败以BLOCKED阻断门禁；npm审计独立记录，不据npm零漏洞推断Python/Cargo安全。实际发行需按docs/engineering/release-gates.md逐Mach-O/PE/DLL/权重NOTICE核对。当前不得发布。
