# 上游 PR 提交记录（2026-10-08）

> 2026-10-08 最终结案：已更新上游并提交六个 PR，idle 已移植、验证并恢复日常配置；剩余旧 refill/tile/dispatch 经当前基线筛选不采用。五项待审查，HC 工作区一项草稿。以下旧“剩余待办”和状态以 [最终结案记录](UPSTREAM-CLOSEOUT-2026-10-08.md) 为准。

后续更新：见 [0.1.40.3 更新与最终 PR 状态](UPSTREAM-UPDATE-2026-10-08.md)。已新增 #1465、扩展 #1457 至完整 HC，四项已转待审查；日常源码与配置也已迁移。以下为较早批次的历史记录。

用户授权逐项提交剩余优化，优先代码简洁、易合并。本批实际已提交并核对以下四个 OPEN/DRAFT PR；没有宣称已合并或已完成最新上游整模型验证。

| PR | 独立改动 | 提交 | 验证 |
|---|---|---|---|
| [#1451](https://github.com/Niko1221/Strata/pull/1451) | PLE host 按需分配，单块只需一份 | b84b1d1 | 64 例真实 CUDA DMA、CMake/CTest、两种 prefill 编译 |
| [#1454](https://github.com/Niko1221/Strata/pull/1454) | embedding 读完后复用为 half 输出 | 304f325 | 两种 prefill 编译、生命周期检查 |
| [#1455](https://github.com/Niko1221/Strata/pull/1455) | 安全特殊 token 边界上的分词复用 | 94befce | 最终联合 273 项测试通过，76.347 秒 |
| [#1457](https://github.com/Niko1221/Strata/pull/1457) | HC gate 使用现有共享 scratch | efbbb26 | 两种 prefill 编译、生命周期检查 |

全部直接基于 d5ea713 / v0.1.40.3，没有堆叠依赖。#1454 和 #1457 都修改 prefill 分配区域，虽然各自独立，先后合并时仍可能需要解决相邻行冲突并复验组合。干净工作树为 `C:/Users/Winge/Documents/Playground/Strata-optimization-pr`，当前分支 `codex/prefill-hc-gate-reuse`，工作区干净。

#1454 在 T=32768 时去掉 320 MiB float payload；#1457 去掉 1280 MiB gate payload。这是分配量计算，另有 allocator rounding，不能当成端到端速度测量。#1457 只提取原 HC overlay 中生命周期清晰的 gate，保留 xn/xn16、low parts、lo/lo16 等独立空间，避免一次移植整个旧布局。region 大小和 bytes_needed 同时包含 gate 需求，保留 ring-byte 两种估算模式。

#1455 明确归属 gputier 的 #567 算法，当前开放 PR 标题扫描未查到同类重提版本。原 #567 因历史重写关闭，不是拒绝。用户本次授权后，从本地参考材料改为有明确来源的独立适配 PR；protected literal spans 仍完整编码。早期联合测试中的夹具失败保留历史，最终修正后的联合测试全部通过。没有借用旧 fork 的 TTFT 数据为新端口背书。

## 其余技术的处置

- 完整 HC overlay：本批只发布 gate 部分。其余 normalized/low-rank 空间不随之移植，需覆盖新版提前归一化、padding、BF16x2 和跨设备路径。
- decode 融合内核：独有代码仍存在，但原 tuning31 的组合收益不能证明单个内核优于最新上游；本批没有发布未比较的替代内核。
- Windows staged refill：最新上游源和 arena 接口已重构，且开放 #1237 已处理 pinned stage buffers，#1323 处理 batched stager reads，不能把旧文件整体提交或重复包装同一改进。
- idle session TTL：与上游 conversation_file、idle unload 及开放会话缓存 PR 存在交叉；原实现需重新设计生命周期，不是可直接移植的小优化。
- 已上游覆盖的 SIMD、Top-K、KV、异步 commit 等不重复提交；个人画像/参数和负实验不进入 PR。
- 40K selector、MoE alias、取消和检查点未资格化分支维持此前结案，不重启长时间扫描。

这些项目未提交，不意味着已全部吸收或已完成验证。全技术族清单和证据入口仍见 [全仓库审计](UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md)。本批收尾后没有后台测试运行，没有建立新的自动化任务。

## 证据与日常环境

发布回执：`bench/results/2026-10-08-upstream-pr-preparation/publication-batch-2.json`，包含远端 head/base、状态和 diff 计数；每个 PR 正文也保存在该目录。

本批日志：`E:/strata-setup/upstream-pr-20261008/prompt-final-tests.log`、`embedding-compile.log`、`hc-gate-compile.log`。C++ 检查是 translation-unit 编译，不能描述为完整链接或完整模型运行。

最终重新核对日常 prefill.cpp / strata.exe / strata-256k-int8.json SHA256，分别仍为 adb14e27…、40a3e767…、9a2faa6a…，没有改动日常实现、二进制或配置。
