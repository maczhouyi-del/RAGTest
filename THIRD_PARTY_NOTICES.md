# Third-party notices — local P0 development draft

本项目尚未对外发布。本文件与`docs/legal/license-texts/`、依赖inventory、lockfiles一起使用；不会用本说明替换上游完整条款。发行包的完整NOTICE与运行时审计尚未完成。

已保留的上游版权和许可文本见`docs/legal/license-texts/{python,npm,cargo}/`。PDFium包含多种第三方组件；pypdfium2 wheel的全部可见BUILD_LICENSES已保留。PyInstaller的COPYING含bootloader exception。依赖版本、来源/hash和缺少本地源包的条目见inventory。

测试PDF未修改：

- Jacob Devlin, Ming-Wei Chang, Kenton Lee, Kristina Toutanova (2019), *BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding*. [ACL Anthology](https://aclanthology.org/N19-1423/)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。
- Vladimir Karpukhin et al. (2020), *Dense Passage Retrieval for Open-Domain Question Answering*. [ACL Anthology](https://aclanthology.org/2020.emnlp-main.550/)，[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)。

PDF哈希、来源与许可核对依据在`tests/fixtures/public/manifest.json`；这些文献是被测资料，不能当作本系统科研质量结论。

候选模型intfloat/multilingual-e5-small，revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`，官方[模型卡](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3)声明MIT。权重与tokenizer仅在`.tools/models/`做经用户批准的本地试验，未随默认app打包；精确文件hash和来源见`docs/legal/model-register.json`。

生成候选Qwen/Qwen2.5-1.5B-Instruct-GGUF，revision `91cad51170dc346986eccefdc2dd33a9da36ead9`，完整[上游固定版本](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/tree/91cad51170dc346986eccefdc2dd33a9da36ead9)的README和Apache-2.0 LICENSE已本地保留于`docs/legal/models/Qwen2.5-1.5B-Instruct-GGUF/`。用户仅批准本地候选试验；权重SHA和下载证据在continuous-2026-10-24目录。llama-cpp-python0.3.36及传递依赖的本地可见许可见更新inventory/license-texts；开发预览包含候选推理运行时，不包含模型权重。完整二进制署名/再分发审查未通过，不作为发行包。

OCR候选tesseract-ocr/tessdata_fast 4.1.0，固定commit `65727574dfcd264acbb0c3e07860e4e9e9b22185`。eng/chi_sim两文件逐一核对官方Git blob/大小并登记SHA256，完整Apache-2.0 LICENSE位于`docs/legal/models/tessdata-fast-65727574dfcd264acbb0c3e07860e4e9e9b22185/`；见`docs/legal/ocr-model-register.json`。权重仅项目内获批试验，不随app分发。tesserocr2.12.0绑定MIT原文已保留；本机轮子附带Tesseract5.5.3/Leptonica1.87.0及图像库，11项动态库hash/链接清单见`docs/legal/ocr-native-inventory-macos.json`。完整原生组件NOTICE/Windows审计未完成，不发布。

OCR工程样本从上述已许可BERT原PDF第1页在本机以200dpi灰度栅格化，形成只含图像的派生PDF。原始论文PDF未改写；派生样本及试验输出保留原作者/题目、CC BY4.0、原件SHA和页码、转换参数及派生SHA，详见continuous证据OCR记录与工具。栅格化和OCR文字属于测试转换，不能把OCR转写当原始PDF逐字符无误。

Docling候选补充（用户已明确批准）：docling-slim2.142.1/docling-core2.104.0/docling-ibm-models4.0.4，以及锁内PyTorch/torchvision/Transformers/OpenCV-headless等可选运行时，实际96项Python及原文许可见docs/legal/dependency-inventory-20261024T150911846052Z.json。固定Heron与TableFormer fast的资源、SHA和下载来源见docs/legal/docling-model-register.json，模型卡/Apache-2.0全文/CDLA-Permissive-2.0官方HTML见docs/legal/models/docling-candidates/。两个仓库元数据通过hf-mirror取得，直接官方HF TLS失败，不能声称独立验证了镜像元数据。docling-models仓库级多许可证未逐文件映射，TableFormer最终再分发范围仍待审；所有模型权重均不随.app打包，未对外分发或最终选型。
