# 离线OCR候选实现契约 v0.2

需求v1.1 §§3、4.1–4.2、7.2、9；用户明确批准的 tessdata_fast 4.1.0 eng/chi_sim 本地候选。原SourceAnchor/EvidenceSpan草案字段保持兼容；本契约新增可选API/诊断字段，不决定最终解析/OCR版本，不代替Docling布局表格解析。

- Rust原生目录选择→`purpose=ocr`一次性、300秒、身份/符号链接限制的授权；`POST /v0/ocr`只接收model_grant_id与幂等键，后台verify任务。只校验固定文件名与登记SHA256，不自动下载、不接受任意模型或命令。
- `GET /v0/ocr`返回configured/公开完整fingerprint/candidate_only，不返回私有目录。隔离worker初始化成功且租约仍有效时，配置和任务成功在同一短事务发布；失败保留旧配置。
- `POST /v0/documents/{version}/parse`新增可选`use_ocr`，默认false，兼容旧快路径/幂等payload。true时重查已批准配置和文件SHA，把OCR完整指纹加入ParseRun指纹与审计事件。
- 既有PDFium受监管子进程只处理固定PDF对象；原生文本少于24个非空白字符的页才渲染200dpi灰度图并识别。两语言eng+chi_sim、LSTM_ONLY、PSM AUTO（不做OSD）；无额外语言数据/在线推理。
- 资源限制：PDF≤500页、每页≤50000字符、总文本≤1500000字符，OCR≤40页、渲染≤8000000像素/页、单进程CPU上限240秒（POSIX）、OCR墙钟300秒/快路径40秒；父进程100ms检查取消/租约并终止其创建的确切子进程。每个工作进程stderr最多保留1MiB并标记截断。不是完整OS安全沙箱或Windows内存隔离结论。
- 输出超限/模型不匹配/取消/失租不得发布。新批次事务提交后才撤下旧Chunk；发布前再次检查版本仍可用于研究。原始PDF不可变。
- 页质量区分text_extracted_unreviewed、ocr_extracted_unreviewed、ocr_low_confidence_unreviewed、needs_ocr_or_review、failed。OCR平均置信度<60、空白、识别/像素/页数失败保留partial；60是候选工程阈值，不是字符准确率或科研达标线。
- `parse-diagnostics`返回最近批次公开配置与页method/mean_confidence/quality，不暴露目录。OCR片段来源为page_only、bbox_norm=null，reason_if_degraded明确OCR未核对，证据卡/阅读器/报告提示。quote一致只证明匹配OCR文本及该PDF版本，不证明字符、数值和单位正确。
- 模型权重不进入app，tesserocr/native运行时仅显式`--include-ocr-lab`打包。当前Mac轮子最低平台标签macOS15 arm64，其他Mac/Windows DLL/干净机仍独立验证。最终再分发许可证审查未完成。

实际revision、Git blob、SHA256、许可证：`docs/legal/ocr-model-register.json`。真实试验使用已许可BERT第一页本地栅格化，保存转换参数与原件SHA；不是用户扫描语料/人工金标。工程功能与OCR质量/科学结论分别报告。
