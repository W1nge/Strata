# Part2: prefill staging memory and upstream Pascal update — 2026-10-08

本轮已为日常 coding 配置安装预填充文件页释放补丁，并更新到上游 **0.1.40.4**。明确、可复现的收益是长提示词阶段的 RAM 余量：补丁的两轮对照中，可用内存中位数从 **0.435–0.476 GiB 提高到 11.613–11.820 GiB**；最终 0.1.40.4 验证为 **11.404 GiB**，最低 **10.690 GiB**。这些是指定请求区间的系统采样，不能当成启动阶段或全生命周期的最低余量。它没有减少物理 SSD 读取，也没有建立稳定的整机提速百分比。

仍用 `C:/strata-models/run-iq3xxs-dual-p100-coding.bat` 启动。配置现在使用 `E:/strata-setup/part2-prefill-next/prefill-release-01404/strata.exe`，并增加 `STRATA_FILE_RELEASE=1`。程序 SHA256 为 `f2c666401bf8264ed666a616cee19c852f86b321bc0c9cc61d8fa784fd07f63f`，构建源码为 `25377113e1172d67822fb068333393a59699d248`，随后只补充了接口注释。配置 SHA256 为 `1e1041b39bfc9c51b06b265733a6b84f3183e6affbe81c9c2c3b36c75340c013`。保留 spec8 / min-p0.9、short-read1024、1024 MiB 显存预留、8192 上下文、INT8 KV、默认 CPU 线程池和既有专家画像。

硬件仍为 i7-13850HX / 32 GB RAM、2080 Ti 22 GiB / 310 W、P100 16 GiB / 250 W，Windows WDDM、无 P2P，驱动 **537.13**。2080 Ti 跑主干和 MTP，P100 跑辅助专家，CPU 专家补集约 10.84 GiB，经 VirtualLock 驻留。模型是 Qwen3.8-Flash-Next IQ3_XXS。双卡与 CPU 容纳 decode 所需专家，不代表长提示词也不再访问 SSD：批量 prefill 会借用、重填主卡缓存，并重新读取文件来源的专家。

旧的 `STRATA_FILE_RELEASE=1` 已覆盖 GPU 缓存上传和重填，却没有覆盖 prefill Stager 的主机复制。长提示词读取映射权重后，文件页继续占据进程工作集，重复堆积约 14 GiB。现在稳定指针的 staging job 也保留来源和 layer/expert ID；直接指针用 memcpy，临时 blob 仍由来源的 `copy_blob()` 复制。Windows worker 在主机复制完成、发布 ready 之前调用已有的 `release()`，随后 DMA 读取独立 staging buffer。文件映射继续有效；来源只处理完整文件内页，保留共享边界页、私人 RAM 副本和固定缓冲区。默认关闭，沿用现有开关，无新增机型判断或调参框架。

生产逻辑只改 `src/prefill/prefill.cpp`，+10/−5 行；连同接口注释和使用说明，独立上游补丁合计 **3 文件、+18/−12 行**。普通整层 streaming 和按路由选择专家的 staging 都保留来源信息。没有改变量化、归约、专家分配或模型采样策略。

以下隔离补丁的比较均使用 0.1.40.3：`control` 为旧程序、已有 release 开关打开，`candidate` 为补丁程序、同一开关打开。实际顺序为 control-a → candidate-a → candidate-b → control-b；每个进程重复两轮，共 18 个请求，覆盖问答、短代码、928 /1924 /5107-token 检索、平方列表、DNS 说明和缓存复用。`plain-a` 是旧程序原有关闭开关的初始基线。

| 测试 | 18 请求合计，秒 | 四个 2K/5K 提示词处理合计，秒 | 可用 RAM 最低 / 中位 GiB | C 盘物理读取 GiB |
| --- | ---: | ---: | ---: | ---: |
| plain-a，旧版 release 关闭 | 135.617 | 93.567 | 未按相同区间采样 | — |
| release-control-a | 141.958 | 97.153 | 0.071 / 0.476 | 54.062 |
| release-candidate-a | 122.016 | 79.443 | 9.941 / 11.820 | 63.867 |
| release-candidate-b | 128.073 | 86.505 | 10.850 / 11.613 | 64.423 |
| release-control-b | 128.177 | 85.164 | 0.090 / 0.435 | 61.563 |
| 01404-general-a，补丁加上游更新 | 127.000 | 84.693 | 10.690 / 11.404 | 63.313 |

内存/磁盘采样约每秒一次，区间为 `3 <= completed_requests < 请求总数`，即前三个短请求之后，直到最后响应之前。C 盘对应 PhysicalDrive2，计数为系统级物理读取，包含该盘的其他活动，边界有采样误差。较早控制组和候选组的文件来源 blob 次数相同，不代表物理 SSD 读次数相同。文件页释放是工作集提示，不保证 Windows 丢弃缓存，不等同于降低 committed memory。

两组 candidate 的 36 个响应与 control-a 对应输出逐字相同，输入/输出 token 数也相同。合并两次启动的完整请求耗时少 7.42%，但反向的一组几乎持平，长提示词甚至稍慢。因此不能把首次约 14% 或合并 7.42% 写成稳定加速。系统调度、动态时钟、文件缓存和首次 CUDA graph 捕获均会影响结果；没有随机化、多机器样本或置信区间。采用理由是恢复约 11 GiB 可用 RAM，接受重复文件读取的取舍。

长代码回归每次 12 个响应、两轮，八个长输出来自 utilities、ttl_cache、algorithms、matrices，共 6992 个输出 token。吞吐按总输出 token / 总 decode 时间计算，排除短 probe 和模块编辑。其提示词仅 256–303 token，使用验证窗口路径，不能把小幅吞吐波动归因于 staging 释放。

| 测试 | 八个长代码加权 token/s | 八个完整请求合计，秒 | 两次 878-token 模块编辑，秒 |
| --- | ---: | ---: | ---: |
| coding-control-a，原 0.1.40.3 | 88.30 | 96.503 | 17.491 / 17.648 |
| coding-candidate-a，0.1.40.3 加释放 | 89.38 | 95.104 | 17.329 / 17.607 |
| 01404-coding-a，加上游 Pascal 修复 | 90.29 | 94.084 | 19.189 / 19.420 |

前两行的 12 个响应逐字一致。上游更新后的八个长代码和两个 probe 仍一致；两个编辑回答各由 931 增至 1052 token，均通过相同功能检查，但请求变长。完整 12 请求合计由候选的 132.346 增至 135.024 秒，不能概括成所有任务都提速。最终通用 18 请求中，16 个回答与 0.1.40.3 候选一致，两个 DNS prose 回答变化，检查通过。有限的代码/格式检查不代表全面的模型质量评估；本轮没有建立持续 115 token/s 的结果。

另用 `short-read448` 跑了两个 probe 和两次 878-token 模块编辑，覆盖按路由 staging 分支，4/4 通过，并与前轮 `mapped-output-b` 对应回答逐字相同。两次编辑为 30.251 /27.990 秒，提示词分别 17.008 /15.485 秒，均输出 1048 token。前轮同路径第二次编辑曾为 14.90 秒；进程内请求顺序及上游版本不同，这不是隔离性能对照，却说明释放文件页可能损失预热后的缓存收益。因此 coding 继续用已验证的 1024 阈值，上游默认开关仍关闭，通用配置没有一并启用。

上游 `fbb362425c891be007b52b9722e27eaf7c4664c9` 为 Pascal 恢复 `__restrict__` 只读缓存访问，并关闭无用的 PDL 预取；`6674a0065fb96bacde33e3eb10f91a1df86f95f2` 更新到 0.1.40.4。P100 符合 `__CUDA_ARCH__ < 700` 的条件。**这是上游作者的修复，不是本地原创补丁，也不放进本次 PR。** 集成版用 MSVC / CUDA 12.4.131、`60-real;75-real`、实验 SM60 支持构建成功。

两张卡的 `mmvq_multi_parity` 和 `native_expert_parity` 均通过，后者使用真实模型 layer0、1、8、12；两个版本的 `file_expert_source_test --rotation-gpu` 在 release0/1 下均通过。`pdl_parity` 两张卡都在 `cudaGraphGetEdges_v2` 处退出 2，不能标成通过。独立 API 探针确认本机 driver interface=12020、runtime=12040：相同空图的旧 `cudaGraphGetEdges` 成功，新 v2 返回 invalid argument；失败发生在图回放之前，两卡 `pdl_supported()=0`。保留诊断记录，没有为此更新驱动。最终集成程序的 12 个 coding、18 个通用、4 个短批量响应全部通过。

另外两组参数没有采用：1792 MiB 显存预留让通用序列从 135.617 到 122.218 秒，但混合生成吞吐由 75.26 降至 71.25 token/s，并改变部分输出；保留 1024 MiB。8 个 Stager 线程和 32 个环形槽位为 120.536 秒，2K/5K 收益不一致，落在本轮波动范围，保留默认值。

诊断轮 `trace-a` 同时启用 `STRATA_TRACE=1` 和 `STRATA_PREFILL_TIMING=1`：前六个请求通过，2K 提示词变成 71.9 秒，5K 在 layer19 触发 60 秒无进度保护、HTTP 503。日志显示 spec8 已缓存八种 CUDA graph，额外 GPU 计时扰动了此环境；普通轮次未复现，尚不能证明单一根因。该轮不纳入正常性能结论，dump 留在本地，不公开提交。本轮共 13 次串行模型启动，12 次完整成功、184 个响应；另有失败诊断中的六个已通过响应，共保留 190 个响应。没有在模型运行期间编译。

安装只改 coding JSON 的 exe 和现有 env，除逐轮 log 路径外，与最终 coding 测试配置一致。通用 spec4/0.8 和单卡 256K 配置逐字节保留。旧程序仍在 `E:/strata-setup/part2-mapped-output-20261008/strata.exe`，旧 coding 配置保存在 `E:/strata-setup/part2-prefill-next/rollback-coding-config.json`；复制回原 JSON 即可回退本轮程序和开关。日常源码已同步本轮引擎和上游更新，用户修改的 `UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md` SHA256 仍为 `d59c6e2b2f686b45ff46574667bf0ee2425b5a6b1a930cca381e15d0d03d184a`。测试进程和 18997 监听已结束。

原始记录在 `E:/strata-setup/part2-prefill-next`，归档为 [bench/results/2026-10-08-part2-prefill-staging](../../bench/results/2026-10-08-part2-prefill-staging)。保留每轮配置、完整响应、engine/server 日志、每秒监测、构建与测试记录、安装回执、回退配置和补丁；较大日志 gzip 压缩，清单同时记录压缩前后 SHA256。程序、模型和 dump 不提交。`summarize_final.py` 可从 JSON 和 gzip 监测日志重算汇总；`receipt.json` 记录最终文件清单。独立 PR 分支 `codex/windows-prefill-staging-release` 基于 `6674a00`，单提交 `9ee824e4cfb620246a01e8dea14fdb1635068f76`，只包含上述三文件差异。

复现实验时使用同一模型、可用的兼容程序、空闲端口和新 label，并保持串行。在其他机器先修改归档配置的绝对路径；本机选择不推为通用性能默认值。前轮映射 helper 输出及 short-read1024 的来源见 [PART2-MAPPED-OUTPUT-2026-10-08.md](PART2-MAPPED-OUTPUT-2026-10-08.md)。
