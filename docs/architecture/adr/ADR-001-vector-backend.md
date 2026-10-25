# ADR-001 向量后端与持久记录边界

- 状态：PROPOSED；决议 OPEN；日期2026-10-24；批准人待用户确认。
- 关联：D01/D09，P0-05/06/08；v1.1 §§3.1–3.6、9.5。

## 问题与候选

SQLite 是真值；Embedding 必须独立于可重建索引持久复用。候选 A 为 SQLite+sqlite-vec；B 为 SQLite+本地 LanceDB；ANN 暂缓到 exact 性能证据不足时另提。普通导入只增量 upsert/delete，全量更换才建立 IndexGeneration。相同内容向量可共享，但 Chunk→版本来源不能合并丢失。

## 证据和裁定方法

当前没有安装、Windows 打包或性能证据。[sqlite-vec KNN](https://alexgarcia.xyz/sqlite-vec/features/knn.html) 有 vec0 与普通表距离函数路径；[LanceDB exact](https://docs.lancedb.com/search/vector-search) 提供 exhaustive/bypass index 路径。公开文档支持可行的实现方向，不能证明本项目兼容/达标。

按 P0-benchmark 使用相同冻结 float32/距离/归一化/查询/授权集合/tie-break/机器，登记原始向量哈希、correctness、P50/P95、增删、冷/热启、内存/磁盘、中文路径、备份/恢复和许可证。用独立精确求解器对受限集合验算；空间拒绝、NaN/Inf、孤儿向量/删除范围测试必须通过。

## 提议与回退

先执行两个适配器同台比较，不预选胜者，不添加数据库服务或默认 ANN。跨存储状态发布/对账而非假设原子事务；同内容复用辅助关联在 schema 冻结时审查。失败保留日志，未校验的新索引不可发布；旧 ACTIVE 继续使用。改后端保留持久 Embedding 与原件，通过 STAGING 校验后切换，不删除竞争候选证据。无数据保持 OPEN，选型须用户批准。
