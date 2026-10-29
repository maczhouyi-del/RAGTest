# RAG-02：参考企业/开源项目的API问答全链路检查与优化

用户2026-10-27要求结合当前项目检查、优化意图、查询改写、召回、检索与重排，并追加参考其他企业/GitHub项目。授权本地代码/测试/文档；不复用已完成RAG-01的单次推送、付费API或外发授权。基线main/b47fa877fb6c7b07f3e95fdfa0ebd5bcf9df996b，工作区干净。

交付日期2026-10-28（Asia/Shanghai）；证据目录沿用任务开始日RAG-02-2026-10-27。

## 参考与适用边界

- Dify Knowledge Pipeline：分阶段观察、元数据/引用随上下文流转。
- RAGFlow Search Settings/API：召回候选、重排候选与最终Top N分离，阈值取舍需实测。
- Haystack DocumentJoiner/MultiRetriever：各通道独立Top K、同范围检索后融合。
- LlamaIndex QueryFusionRetriever：原查询保留，额外查询生成是独立、可关闭的模型步骤。

只参考官方文档/仓库，链接和检查日期写入报告。不复制企业默认阈值或规模、架构、模型依赖；未经人工金标不宣称提升、不默认启用模型重排。

## 实现顺序、文件与验收

1. 审查真实React→Rust→API→Workbench→Provider调用和已有引用/范围校验，跑基线；解释API只接收选中片段及有界上下文，并不直连SQLite。
2. `workflows/system_information.py`：混合问题仅去掉完整系统子句，保留科研子句内部标点/and/并行等词；科研内容不丢失。
3. `workflows/workbench.py`及小型查询工具：上下文限定同版本/项目/解析批次；避免非指代it误补历史；记录实际查询、输入与策略，不自动用云模型改写。
4. `retrieval/source_search.py`：显式引号短语优先，BM25/OR作为扩展；保留通道原排名、文本/偏移/范围，合成反例证明精确短语不被单词噪声挤走。无引号保持旧策略，不擅自加科学同义词。
5. `retrieval/hybrid.py/reranking.py`及Workbench：显式review策略先取有界较大候选池再重排、最后≤8/默认每篇3；最多每批6、总候选12的本地实验预算，默认关闭、额外代价如实记录。原始rank及同分/来源边界不变。
6. Workbench/`models/{provider,network_provider,local_generator}.py`：推理/外发前重查冻结来源，编号片段保留经SQLite确定的来源分组/页信息；记录实际截取与模型输入，严格引用与失败拒发继续有效。保留API授权检查，不发送新范围历史。
7. 增加各阶段耗时/数量诊断及回归，更新`contracts/retrieval-answer-v0.7.md`、PLANS与本轮报告/验证索引；必要的前端类型/诊断展示仅增量修改。无schema迁移、新依赖或模型下载。

## 命令与门禁

使用`tools/run_logged.py --directory docs/engineering/evidence/RAG-02-2026-10-27`保存命令、平台、UTC时间/退出码和失败输出。最小失败测试→修复→分阶段回归→完整pytest（显式已有E5/OCR/Docling）、Ruff、TS/Vite、Rust及浏览器受影响链路；冻结侧车使用新隔离构建目录，不覆盖旧产物、不删除失败目录。测试全部用隔离工作区/loopback协议fixture，真实模型工程测试与科研人工金标分列。

验收：纯系统0检索/推理，混合科研文本完整；新范围无旧范围历史/原文外发；来源失效后下一次API请求0；显式短语不受OR噪声挤出；重排能提升池中原本未进最终8的候选且最终配额有效；引用仅限本轮实际输入；失败/拒答/阶段诊断明确。真实收费API、人工金标、千篇容量及干净Windows不具备资源时BLOCKED，不阻断独立工程修复，不标正式发布通过。

## 执行结果

上述工程修复完成：最终Python297通过/0失败/0跳过；Rust6通过/3 ignored；TS/Vite、Ruff、静态kit、浏览器88检查通过。新最小冻结产物与当前源码哈希相符，保留旧产物。实际失败、命令、官方参考、调用链和质量缺口见[报告](../reports/RAG-02-2026-10-28.md)及[RAG-02-validation.json](../reports/RAG-02-validation.json)。Windows、真实千篇、人工科研金标和真实付费API生成保持BLOCKED/NOT EXECUTED；当前本地改动未提交/推送。
