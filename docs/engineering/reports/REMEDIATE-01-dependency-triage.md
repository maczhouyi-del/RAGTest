# REMEDIATE-01 依赖分诊（2026-10-30；发布阻断）

648个源码锁物料，OSV querybatch确认7个包/9条数据库记录。原始坐标和响应仅含公共依赖信息，存于本机evidence/REMEDIATE-01。历史GitHub run 40877592619 的OSV为FAIL，但未显示具体发现；本轮没有把它当成已解决。

| 锁定依赖 | 通告/受影响/修复 | 实际路径与处置 | 状态 |
|---|---|---|---|
| diskcache 5.6.3 (PyPI) | GHSA-w8v5-vhqr-4h9v、PYSEC-2026-2447；≤5.6.3；无公布修复 | llama-cpp-python传递依赖。安装源码llama.py默认cache=None，本工程未构建LlamaDiskCache/未调用set_cache/未指定缓存目录；未发现当前问答路径读取pickle缓存。保持无持久生成缓存，不引入该功能。完整生成候选包仍含依赖，发行逐文件审查/确认缓解尚缺，不能豁免。 | BLOCKED |
| block-buffer 0.10.4 (crates.io) | GHSA-qwgh-2vcv-g2f7；通告写block_buffer，范围<0.12.1 | 当前macOS依赖树经sha2 0.10.9/digest 0.10.7进入应用及Tauri构建。通告描述把游标存于buffer末字节的inline实现；本地0.10.4源码是独立pos:u8字段；release另配置panic=abort。疑似范围/版本匹配过宽，但没有上游确认或Miri证据，因此不当误报关闭。0.12.1需要跨semver更新sha2/Tauri传递树，不能盲目只改锁版本。工具保留reported_affected与包名不一致。 | BLOCKED |
| glib 0.18.5 | RUSTSEC-2024-0429、GHSA-wrw7-89jp-8q8g；≥0.15,<0.20；修复≥0.20 | Tauri GTK/WebKit目标依赖；实际macOS tree不存在。Windows离线tree被缺失jiff-tzdb缓存阻断，未冒充Windows产物检查。首版未声明Linux，不能因此宣称全锁安全或自行改Tauri主版本。目标发行SBOM/传递路径核验后才能由负责人判定适用性。 | BLOCKED |
| proc-macro-error 1.0.4 | RUSTSEC-2024-0370；unmaintained；无修复版本 | 维护性通告，不能描述成已确认可利用漏洞；实际macOS tree不存在。替代需上游迁移宏依赖，不盲目改包名或强行patch版本。 | BLOCKED |
| zbus_names 4.3.5 | RUSTSEC-2026-0371；unmaintained；无独立修复 | 通告建议迁移zbus 6 names；当前tauri-plugin-single-instance的zbus依赖由target_os=linux控制，macOS tree不存在。等待相应上游可兼容升级/目标物料审查。 | BLOCKED |
| zvariant 5.15.1 | RUSTSEC-2026-0370；unmaintained；无独立修复 | 通告说明并入zbus 6 wire（GVariant另有迁移路径）。实际macOS tree不存在；首版不增加Linux支持，不强制全树重大升级。 | BLOCKED |
| zvariant_derive 5.15.1 | RUSTSEC-2026-0372；unmaintained；无独立修复 | 派生宏并入zbus 6，macOS tree不存在；同上，未自动标安全。 | BLOCKED |

## 工具结果与限制

Python urllib与npm原生audit均出现TLS/网络失败；显式curl公共坐标传输可访问OSV并取得全部详情。block-buffer包名不一致使总体审计exit2/BLOCKED，已知发现仍完整保存；其他详情不会因一条错误被丢弃。npm curl bulk复核仍网络失败，不能记0漏洞。三份依赖锁未修改：没有发现可在当前调用链直接、兼容地小版本升级并关闭这些发现的充分依据。

下一步：取得可靠npm扫描；上游确认block-buffer 0.10系列的适用范围或同版本独立复现；对目标发行包运行逐平台依赖/物料审核；确认DiskCache路径持续不可达或取得修复版本；维护通告由发布负责人签字处理。不存在自动豁免名单。未处置项继续阻断正式发行。

## 已核对的公共来源

- [DiskCache公告](https://github.com/advisories/GHSA-w8v5-vhqr-4h9v)：攻击者须能写缓存目录，默认pickle反序列化风险，无公布修复。
- [block_buffer公告](https://github.com/advisories/GHSA-qwgh-2vcv-g2f7)：caught panic与inline游标，标注修复0.12.1；本机差异是审查推断，不代替上游结论。
- [glib公告](https://rustsec.org/advisories/RUSTSEC-2024-0429.html)：VariantStrIter不健全，修复0.20。
- [proc-macro-error维护公告](https://rustsec.org/advisories/RUSTSEC-2024-0370.html)。
- [zvariant](https://rustsec.org/advisories/RUSTSEC-2026-0370.html)、[zbus_names](https://rustsec.org/advisories/RUSTSEC-2026-0371.html)、[zvariant_derive](https://rustsec.org/advisories/RUSTSEC-2026-0372.html)维护公告。
