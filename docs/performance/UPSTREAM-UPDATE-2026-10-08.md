# 更新至 0.1.40.3 与优化移植

> 2026-10-08 最终结案：已更新上游并提交六个 PR，idle 已移植、验证并恢复日常配置；剩余旧 refill/tile/dispatch 经当前基线筛选不采用。五项待审查，HC 工作区一项草稿。以下旧“剩余待办”和状态以 [最终结案记录](UPSTREAM-CLOSEOUT-2026-10-08.md) 为准。

日常仓库已从旧 fork 更新到上游 d5ea713（0.1.40.3），并集成五个优化 PR。当前分支 `codex/daily-upstream-01403`，HEAD `848d197b99cebedbe90ec7c87092b3f84866fb48`，已推送 origin。四个旧 PR 不是四个都合并到上游；这里说的是本地集成。

## 实际发布状态

| PR | 最终范围 | 状态 |
|---|---|---|
| [1451](https://github.com/Niko1221/Strata/pull/1451) | PLE host 缓冲按需分配 | OPEN，待审查 |
| [1454](https://github.com/Niko1221/Strata/pull/1454) | embedding 与后续输出复用 | OPEN，待审查 |
| [1455](https://github.com/Niko1221/Strata/pull/1455) | 安全边界分词复用，注明 gputier/#567 来源 | OPEN，待审查 |
| [1457](https://github.com/Niko1221/Strata/pull/1457) | **完整 HC read scratch 复用**，已从仅 gate 扩展 | OPEN，DRAFT |
| [1465](https://github.com/Niko1221/Strata/pull/1465) | 归一化暂存未缩放乘积，避免重新读取/计算 | OPEN，待审查 |

1457 当前 head 为 819881c，只有一个源码文件，34 增 16 删。take_hc 同时用于真实布局与计数，处理 unfused、padding、BF16x2 low parts。默认无 padding、T=32768 的独立 payload 去掉 1980 MiB；还需考虑最大共享工作区与 allocator rounding。1454 的 320 MiB 是另一项。不能把分配量直接当作速度收益。

1465 head 为 e952756，一个源码文件，8 增 16 删。提取旧 gr_norm_stream_kernel 中有效的复用方式，直接简化新版 gr_norm_split_kernel，不带入旧 tuning bitmask 或另一套 kernel dispatch。上游既有 per-device correctness check/fallback 保留。CUDA graph 微测试在 RTX 2080 Ti 上测到 norm 单内核减少约 3.2%–17.1%，不是端到端 decode 收益。

## 验证

- MSVC/CUDA/ggml 原生完整引擎构建通过。ggml 使用上游固定版本 3cf03257。首次链接混合 cudart/cudart_static 失败，显式设置 `CMAKE_CUDA_RUNTIME_LIBRARY=Shared` 后通过，未改生产源码来绕过链接错误。
- PLE 64 例真实 delayed-DMA 测试通过。
- 归一化改动通过现有 fused_gr_selftest：1–8 token、带/无 pending write、plain/split/staged 全输出逐位一致。独立 norm 对照 xn/rs 也逐位一致。
- 四组真实模型纯上游/最终集成对照，共八次成功退出：default、GR_UNFUSED=1、PREFILL_BF16X2=1、RING_BYTES=0。IQ3_XXS、INT8 KV、194 输入 token、128 分块、8 输出 token；各组输出 ID 一致。这不能替代全量 logits/state 比较，也不是速度 A/B。
- 256K 配置启动及短生成通过，实际输入 194 token，自动选择 256-token chunk，189 个 loan slots 补回约 62.5 ms。**没有填满 256K 上下文。**
- 更新后日常路径的 HTTP health/models、首次请求和重复请求通过。关闭 thinking 的两次 `2+2` 均回答 `4`；重复请求有历史命中。最初 16-token thinking smoke 没有足够预算输出正文，另行做了答案检查，不能把前一次只收到 choices 当作回答正确。
- 每轮测试的服务与引擎正常关闭，没有留下模型进程。

完整 HC 的控制向量、padding、多 GPU、HIP/其他后端仍缺 runtime 验证，所以保留草稿。四个可审查 PR 的正文已补充真实模型验证及其范围，没有宣称所有机器已验证。

证据均在 `E:/strata-setup/upstream-01403-integrated/`：`migration.json`（所有 PR 回执及文件 SHA256）、`parity-matrix.json`、`parity-*.log`、`capacity-256k.json`、`http-smoke.json`、`norm-selftest.log`、`norm-probe-final.log`、实际 probe 源码和各次 build 日志。构建脚本为 `C:/Users/Winge/Documents/Playground/build_strata_integrated.bat`。新构建目录在 E 盘，旧日常 build 目录只替换 exe，原 CMake cache 不是本轮验证的构建配置。

## 配置迁移与回退

`C:/strata-models/strata-256k-int8.json` 现在指向同一日常目录中的新 exe。保持现有模型、词表、画像、MTP 资产及 256K INT8 容量；prefill 改用上游 `auto:32768`，最多 32K、按请求和可借空间选择。旧 tiered budget 用 `--resident-budget-gib 8` 和 8 GiB headroom 表达。所有无法识别的旧 fork flags 均移除，完整列表在 `config-migration.json`。

旧的 session-only idle offload 尚未移植，当前配置不再提供它；没有用卸载整个模型的 idle-unload 冒充等价替代。旧个人 decode-tuning、native-tasks、ring 强制值也未自动映射成未测的新默认。此次是上游迁移与贡献整理，不声称新版整体比旧日常版本更快。

回退材料：

- 源码及三个原 tracked 修改：本地分支 `codex/pre-01403-daily-snapshot`，commit `40901546d161ae692709daab8f229557d45c640c`，同时保留对应 stash。旧 `codex/avx-vnni-q2` 历史未重写。
- 原 exe、原配置、原 DETAILS/优化综述/FORK_NOTES/idle-cache 文档：`E:/strata-setup/upstream-01403-integrated/rollback-0138/`。
- 大量 untracked 原始实验报告未删除；旧优化综述/FORK_NOTES/idle-cache 文档在新工作树保留为历史材料，不代表新版功能。

回退时先停止模型并保存更新后的新改动，再切到 snapshot 分支，恢复上述原 exe 和配置。不要对原仓库执行 reset --hard / clean，也不要覆盖新产生的用户修改。

## 仍未提交的独有实现

本次没有把“可提交的五项”误写成“所有历史独有实现都已提交”。剩余重点仍是：

1. Windows 多 worker / 双 pinned 缓冲补回。上游已有队列化补回、并行文件预取及社区 #1237/#1323 的相关工作。本轮 256K 配置短请求中补回仅 62.5 ms / 约 9.7 s prefill，但这不能外推长请求。旧接口不能直接移植，需要在新版长请求上证明独立收益后再决定是否值得增加一套实现。
2. 保留权重的 idle session 卸载/恢复。新版 session allocation、MTP、conversation 文件与缓存生命周期不同。它是独立内存管理功能；还未完成新版设计与验证，本轮没有提交不可工作的工具类或移除兼容检查来凑 PR。
3. 旧 decode 其他 tile/dispatch 组合。此次已提取 norm 复用；其余不能用旧 tuning31 的组合 +11.13% 作为自身收益证据。新版已含 staged、tile 和按设备分支，应逐项比较而非继续发布旧 bitmask。

上游已有的 SIMD/Top-K/KV/异步 commit 等不重复提交；个人画像参数与已结案的失败/未资格化实验维持原处置。剩余移植尚未全部完成；后续从本记录接续，不要重新从旧 0.1.38 工作树假定日常环境未更新。
