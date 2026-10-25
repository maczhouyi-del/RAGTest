# VectorSearchAdapter v0：精确 KNN 的最低语义保证

**候选后端**：A = SQLite + sqlite-vec；B = SQLite + LanceDB。后端选择待 P0 同台实测，不应因本文提前定案。

## 抽象接口（伪签名，非可执行 Python）

```python
class VectorSearchAdapter:
    def upsert(self, space_id: str, entries: list[VectorEntry]) -> UpsertResult: ...
    def delete(self, space_id: str, embedding_ids: list[str]) -> DeleteResult: ...
    def search_exact(
        self, space_id: str,
        query_vector: list[float],
        eligible_embedding_ids: set[str],
        k: int,
        metric: str,
    ) -> list[ScoredVector]: ...
    def check_integrity(self, space_id: str, expected_manifest: Manifest) -> IntegrityReport: ...
    def rebuild(self, space_id: str, persisted_embedding_records: Iterable[EmbeddingRecord]) -> RebuildReport: ...
```

## 不可妥协的行为

1. `search_exact` 必须在**允许的候选向量集合内**求 Top-K。先全库搜 K 条再过滤可能漏掉合法候选，**不满足语义**。如果引擎不支持过滤，应使用等价的受限精确距离计算/分区机制，证明与基线一致，并记录性能代价。
2. 向量维度、模型空间、距离度量、归一化配置必须一致；跨空间查询显式拒绝。
3. 返回稳定 ID、距离/排序依据及被包含的过滤范围；不要把不同后端的 raw distance 直接当作全局统一置信度。
4. 每个结果均再与 SQLite ACTIVE/可见 Chunk 和 DocumentVersion 交集核验；索引中存在但 SQLite 未发布的向量不可成为引用来源。
5. `upsert/delete/rebuild` 必须幂等；异常重试不产生双份发布。同一向量可以多个 Chunk 复用，但证据必须保持 Chunk→DocumentVersion 来源映射。
6. 原始 Embedding 持久化与可重建向量检索结构分离；新论文增量不创建全库世代。
7. LanceDB 与 SQLite 的存储不存在自动跨库原子提交；需 journal/manifest/状态发布与启动对账。sqlite-vec 单库路径仍需实际验证事务、扩展加载、备份可用性。
8. 拒绝无效/NaN/Inf/维度错的 query 和 embedding；拒绝 `k <= 0`、未授权集合、未知 metric。

## 公平评估

按照 `docs/phases/P0-benchmark.md` 同一 Embedding/查询/距离/过滤/Windows 环境比较 exact KNN；记录检索 P50/P95、增删、备份恢复、启动、磁盘/内存及许可。仅当 exact 无法满足已批准性能和召回目标时，才提议 ANN。
