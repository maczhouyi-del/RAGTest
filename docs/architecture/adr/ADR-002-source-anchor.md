# ADR-002 来源坐标字符偏移与降级契约

- 状态：PROPOSED；决议 OPEN；日期2026-10-24；批准人待用户确认。
- 关联：D06/D10，P0-03/04/07；v1.1 §§4.2、6.2、9.3。

## 问题与候选

源文要求可追踪，不指定规范化坐标系。草案采用未旋转可见页左上归一化坐标，但缺显式 CropBox/MediaBox、页面尺寸/单位、变换版本，以及 clean_text_offsets 的锚定文本对象和字符单位。Python Unicode code point 与 JS UTF-16 code unit 对非BMP字符不同，需明确协议后转译。

候选 A：保留原生 PDF point/box/rotation 与变换矩阵，阅读时转换；B：保存草案归一化坐标，同时保留原生几何/变换 provenance；C：未校准前只返回 page-only。不允许通过填写看似合理 bbox 代替校准。

## 证据和裁定方法

当前仅审查 JSON/架构图，无真实 PDF 测试。0/90/180/270、CropBox、双栏/表格/OCR、125%/150% 缩放逐页人工对照 PDFium→PDF.js。定义清洗文本 ID/版本/哈希、半开区间及 Unicode 单位；用中文/组合字符/emoji/连字符清洗反例验证。需要跨页/区域多对多映射，不将单 anchor 误当所有 Chunk 唯一位置。

## 提议与回退

建议先保守 page-only，在足够证据后批准 A/B；page-only 也应能表达没有精确 Element/offset 的可靠页定位。unresolved 是否允许缺 page/element、table-cell 是否必须有可靠 bbox 均需冻结，不能随意填占位数据。统一 SourceAnchor API 与 JSON Schema 版本和必填字段；所有低置信原因可见。变更草案版本并说明兼容；不覆盖旧 ParseRun。校准失败回退 page-only；任何错版本/错页立即阻断发布。
