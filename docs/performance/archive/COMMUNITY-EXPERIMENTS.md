> 历史原始报告（归档于 2026-10-03）。本文的“当前/已启用/未推送”只表示当时状态；最终采用项、纠错和发布状态以 [总总结](../OPTIMIZATION-SUMMARY.md) 为准。本归档仅添加此说明并替换个人工作区路径，未改写测量结论。附件名可能指本机证据包；已公开的小型数据见 [索引](../../../bench/results/2026-10-03-local-optimization/README.md)。

# Strata 社区实测复核与本机实验

2026-10-02。源仓库 [Niko1221/Strata](https://github.com/Niko1221/Strata)，抓取时主线为 `d9ab843`（0.1.35）。本机是在 0.1.24 分支上持续优化的版本；没有整仓升级或覆盖此前修改。

通过 GitHub API 建立 **502 条 issue / PR 的索引（234 个 issue、268 个 PR）**，重点读取 **32 条**记录的正文、评论和相关补丁。仓库未开启 Discussions。数字是检索范围，不表示逐一审计了全部 502 条。

本机：单请求并发，2080 Ti 22 GB、32 GB RAM、AVX2 CPU、PCIe 3.0 x16。保持原模型权重、量化、专家 top-k、88,252 项 MTP 草稿词表、静态专家画像与 32768 上下文。没有改硬件频率、电压，没有安装工具包或推送。

## 已实际试验的五个方向

| 社区来源 | 对方的经验 | 本机结果 | 处理 |
|---|---|---|---|
| [#207 AVX2 权重预取](https://github.com/Niko1221/Strata/pull/207) | Zen 3 完整轮次快约 1.3%；另一 Intel 实测接近零 | 65.686 → 65.752 tok/s，约 +0.10% | 无明显收益，不采用 |
| [#500 CPU 中间激活量化并行](https://github.com/Niko1221/Strata/pull/500) | 作者报告 +69%～78%，但同时缓存命中和接受率大变 | 65.686 → 65.819 tok/s，约 +0.20% | 没有复现大幅提升，不采用 |
| [#284 commit 与草稿重叠](https://github.com/Niko1221/Strata/pull/284) | 原作者约 +5.6%；独立反馈约 +1.3%～2.1% | 正式交替对照 **66.164 → 66.769 tok/s，+0.91%** | 已应用 |
| [#279 Windows 显存余量](https://github.com/Niko1221/Strata/pull/279) | 多留余量解决另一台机器的 WDDM 停顿 | 预留 700 → 1500 MiB，约 65.7 → 62.9 tok/s | 本次变慢，保留原值 |
| [#270 Turing 提示词注意力](https://github.com/Niko1221/Strata/pull/270) | Turing 的 k8 Tensor Core 指令；另一台 Turing 机器 prefill 约 +11%～12% | 数值对照通过，完整模型见下表 | 已应用 |

前三个初筛及显存实验均每配置预热 1 轮、正式 2 轮、6 题；重启前后对照出现漂移，微小差值不能当作稳定收益。commit 的结论来自之后的同进程交替确认。量化并行采用相同独立 (expert, token) 任务与原量化函数，任务容器预留容量；不能把它当作对方整套配置的复现。

显存实验：1500 MiB 预留让实际剩余显存从 324 增到 1124 MiB，同时驻留专家从 8974 降到 8488。它可能有助于显存被桌面程序挤占的情形，本次吞吐却下降。

## Decode 正式确认

同一进程、每题轮换开关顺序、14 题、预热 2 轮与正式 3 轮：**140 个请求，84 个正式请求**。temperature=0、thinking off、max_tokens=256；所有请求均串行。为后续 prefill 对照关闭了提示词缓存，两组相同。统计不含 prefill。

- 三轮提升：0.59%, 1.32%, 0.83%。
- 独立 8 题提升：1.27%。
- 按题目聚类重采样 95% 区间：0.37%～1.34%。
- 39/42 正式输出逐字一致。其余 3 对集中在 `new_zh_probability` 的末尾措辞；两种措辞在 sync 和 async 各自的重复运行内均出现，且都触及 256 token 上限。排除该题，提升仍为 0.82%。这不是全模型逐位一致的证明。
- 此处 66.77 与上一轮 67.13 不能直接相减：本轮缓存设置、顺序和运行状态不同；采用本轮同期对照。

适配包括主线对 #284 的后续审计：commit 后记录事件；请求边界、提示词窗口转批量处理、检查点、生成结束和下一次写 commit 参数前等待；退出析构同步；多卡保留同步。最终等待计入 decode 时间。

## Prefill 完整模型对照

同一进程交替两条注意力路径，提示词缓存关闭，固定保存的输入；每长度每配置预热 1 次、正式 2 次。以下是新读入 token / 输入处理时间，非 decode，也不是客户端流式首 token 的直接测量。

| 实际输入 token | 原路径输入处理时间 | Turing 路径输入处理时间 | 原路径 tok/s | Turing tok/s | 提升 |
|---:|---|---|---:|---:|---:|
| 8,390 | 16.12s / 16.13s | 14.76s / 14.78s | 520.4 | 568.1 | +9.16% |
| 15,956 | 23.62s / 23.68s | 20.71s / 22.52s | 674.7 | 738.1 | +9.41% |
| 31,243 | 46.96s / 47.24s | 39.97s / 41.54s | 663.3 | 766.6 | +15.56% |

每次请求都检查 `cache_n=0` 和隐藏词召回。没有清空 Windows 文件缓存，因此不称作冷盘实验。每长度正式样本只有 2 对，应保留这个限制。

局部数值检查：32K 上下文、256 个查询，INT8 8.933 → 2.874 ms（3.11×）；FP16 8.657 → 3.281 ms（2.64×）；另测 1500/2100 上下文边界，4 组全部通过。相对 FP64 的最大绝对误差约 3.62e-6～4.91e-6，输出尺度约 2.68～3.47。新路径与旧路径不是逐位一致；该测试的误差门限未放宽。局部 3 倍不能当作整机 3 倍。

CPU 量化并行与预取组合、关闭组合，各通过 88,473,600 项精确/sentinel 对照；服务协议 39 项通过，Windows 分层来源测试通过。有限召回与服务检查不等同于全面质量评估。整个仓库 CTest 没有重新全部运行，既有 PLE fixture 缺失仍是验证限制。

## 其余经验的适用性

| 来源 | 结论 |
|---|---|
| [#494 / #501 主线程绑核](https://github.com/Niko1221/Strata/issues/494) | 作者后来确认 SessionLoopScratch 已固定线程，实测均值 -0.3%，主动关闭补丁；本机已有该初始化路径。 |
| [#43 AVX2 多 token i-quant](https://github.com/Niko1221/Strata/pull/43) | 本机已经包含这条路径；不能再次算作新增收益。 |
| [#137 草稿词表缺少 CJK](https://github.com/Niko1221/Strata/issues/137) | 问题真实，但本机上一轮已保留全部含 CJK 字符的词条。 |
| [#258 Turing 1280 分块](https://github.com/Niko1221/Strata/pull/258) / [#315 HC 拆分](https://github.com/Niko1221/Strata/pull/315) | 本机已有较小分块和按流归一化；新流水实现仍有差别，不宣称完全等同或已全测。Turing 没有 cp.async。 |
| [#375 旧 GR_V3 的 Turing 一致性问题](https://github.com/Niko1221/Strata/issues/375) | 上游已限制不合适的两半分块路径；不能仅凭“V3”名字启用。本机未开启该旧实验。 |
| [#343 Turing Tensor Core decode GEMV](https://github.com/Niko1221/Strata/pull/343) | 对方实测比原内核慢 1.3～2.2 倍；与 #270 的批量注意力适用场景不同。 |
| [#407 激进动态驻留](https://github.com/Niko1221/Strata/pull/407) | 要求显存外专家全部在 RAM；当前不满足。作者还说明部分数据包含答案结束后的循环尾部，完整轮次未有显著改善。 |
| [#378 弹性 KV](https://github.com/Niko1221/Strata/pull/378) | 主要针对预分配 262K KV、全部专家在 RAM 的情况；当前 32K + 低 RAM 分层模式不在其适用范围。68% 是缓存容量增幅。 |
| [#413 GDN key-head 合并](https://github.com/Niko1221/Strata/pull/413) | 主要新内核要求 sm_80+ 的 cp.async，2080 Ti 不满足；输出归一化子改动需另行衡量。 |
| [#42 大页](https://github.com/Niko1221/Strata/pull/42) / [#489 Linux hugepages](https://github.com/Niko1221/Strata/pull/489) | 大页初始化修复已有部分代码；Linux 完整 arena 的报告不能直接套到当前 Windows cudaHostAlloc 分层缓存。没有修改系统权限或大页设置。 |
| [#139 BF16→FP32 SGEMM](https://github.com/Niko1221/Strata/pull/139) / [#225 staging](https://github.com/Niko1221/Strata/pull/225) | 修订后的完整模型收益接近零；同型 22GB 2080 Ti 反馈某些 staging 设置变慢，优先级低。 |

## 后续仍值得专门适配的候选

1. [#362 Windows 非缓存读取](https://github.com/Niko1221/Strata/pull/362)，依赖 [#357](https://github.com/Niko1221/Strata/pull/357)：与本机 32GB 内存压力最贴近。作者在模拟 32GB 条件下改善了预算保留、加载和 prefill；需适配本机已修改的 tiered source，保留热态缓存收益并核对文件窗口生命周期。本轮未实测此补丁。
2. [#439 批量专家 gather](https://github.com/Niko1221/Strata/pull/439)：相同 IQ3_XXS、PCIe 3.0、DDR4 的独立报告，长输入 +3.6%～4.3%；需审计 staging ring 归还和 DMA 消费事件。本轮未实测。
3. [#374 PLE 首块读取重叠](https://github.com/Niko1221/Strata/pull/374)：原作者 prefill 约 +3%～5%，另一台 PCIe 3.0 NVMe 机器约 +1%；收益受 SSD 和层 0 可遮蔽的时间限制。本轮未实测。

这些是候选，不是尚可保证获得的百分比。多卡、NVFP4、剪枝模型及改变 top-k 的报告不符合本轮硬件或模型约束。

## 复核材料

- `community-summary.json`：本机各组原始聚合指标。
- `strata-community.patch`：相对本轮开始前源码的增量，保留此前优化。
- `community-evidence.zip`：公开来源快照、脚本、请求、日志、前后源码及可执行文件；不包含模型权重。

生产配置仍为 `C:/strata-models/strata-iq3xxs-native.json`。具体生效参数及回归以该配置和证据包为准。此前偶发 CPU 执行异常的根因仍未确认，性能测试通过不表示该历史问题已被修复。

## 日常服务最终回归

已按生产配置启动，日志确认 async commit 与 Turing prompt attention 均开启；32768 上下文、服务健康、无在途请求，仅一个引擎进程。同步/异步两组各 6 项会话检查通过，其中连续/分支/返回请求实际各复用 37 token；长度截断后的下一请求正常。额外 16K/32K、10%/90% 深度召回 4/4 通过，32K 实际约 31,241 token。此前 prefill 交替测试的 18 个中部召回请求也全部通过。
