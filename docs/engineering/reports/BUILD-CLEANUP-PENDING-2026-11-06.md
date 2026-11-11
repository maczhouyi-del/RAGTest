# 历史构建产物手动清理清单（2026-11-06）

**后续状态（2026-11-07）：用户明确允许本次清理后，下列11目录及随后6个过渡构建目录均已实际删除；不再需要手动处理。** 17目录/176文件，可用空间实测增加12.376GiB，89份诊断先归档核验；详见[BUILD-CLEANUP-02报告](BUILD-CLEANUP-02-2026-11-07.md)。下文保留2026-11-06盘点时的历史状态。

状态：仅盘点，实际删除 0。按用户 AGENTS 的禁止批量删除规则，请用户在 Finder 中手动处理下列候选目录；不要删除整个 .tools/build。源码提交/测试不依赖此清理。

保留最新 VERIFY-CLEAN-SYNC 侧车/工作目录、上一份 SECTION-AWARE verified 回退候选、最后 GUI App 与 CHAT-02 侧车；模型、用户数据库、PDF、target、dist 不在清理范围。历史失败日志及关键构建诊断已另行保存在本机 evidence/VERIFY-CLEAN-SYNC/preserved-build-diagnostics。

| 具体绝对路径 | GiB | 运行进程 |
|---|---:|---|
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/CODE-CLEANUP-sidecar` | 0.413 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-sidecar` | 0.413 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-v2-sidecar` | 0.413 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/SECTION-AWARE-v3-sidecar` | 0.413 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261101T143731118685Z` | 0.941 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261102T072258087103Z` | 0.941 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261105T115036194529Z` | 0.964 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261105T120004669614Z` | 0.951 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032257247225Z` | 0.952 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032731396803Z` | 0.965 | 未发现引用该路径的进程 |
| `/Users/kabudamac/CodexWorkspace/Web-projects/projects/RAGSystem/.tools/build/sidecar-20261106T032854876253Z` | 0.951 | 未发现引用该路径的进程 |

候选总计 8.318 GiB；不是已回收空间。盘点时进程检查不能保证未来无程序使用，手动清理前应关闭旧开发程序。
