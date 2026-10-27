# 容量验证口径（HARDEN-01）

工具：`engine/.venv/bin/python tools/capacity_benchmark.py --kind real --manifest <获准本地manifest> --model-directory <既有E5目录> --output <本地证据目录>`。默认递增10/50/200/1000篇，必须有相同数量**不同SHA**、有明确license与本地路径的样本，不下载、不复制两篇冒充1000篇。语料不足exit2/BLOCKED，不导入用户资料。显式合成试验用`--kind synthetic`，每份仅一页短文本，文件标SYNTHETIC，不用于科研/真实容量签字。

每级记录硬件/OS、篇/页/字节、可见Chunk与持久向量、增量导入/解析/索引秒数、重复构建new_embeddings、备份/恢复秒数、恢复重建0新编码与向量字节一致、保留备份后的磁盘总量。RSS为分别的主进程与子进程高水位，不能相加当同一时刻进程树峰值；Windows需另加工作集采样。元数据提取与生成不在计时内。

检索预热后默认20次，分别报告含query Embedding总时延、测得编码时间及总时延减编码的近似检索部分；后者仍含合法性/状态等本地开销，不能解释为纯向量核耗时。P50/P95为这组有限样本次序统计量，不代表充足置信度或SLA通过。首次/增量及恢复重建分别计数，不能把恢复用持久向量复建当新的Embedding。

方案P95≤1秒只是建议初始目标，16GB CPU且不含queryEmbedding/Reranker/LLM，需真实语料/机器/批准口径后审查。真实1000篇、4–8万Chunk、2–5GB PDF当前缺语料，BLOCKED；合成1000个微小PDF无法解除该门禁。8GB/Windows/非管理员/Defender条件另测。本工具创建新.tools/test-data子目录，保留所有失败与备份，不清旧数据。
