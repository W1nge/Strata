# FORK_NOTES — W1nge/Strata (turing-tiered-win)

本 fork 的全部偏离上游之处。基准：upstream/main @ 0.1.24 (3ce2523)。

## 组装的社区 PR

| PR | 内容 | 状态 |
|---|---|---|
| #87 | Turing port：运行时门槛 cc 7.0、fused_gr 共享内存切片（64KB 卡 → 6-token 分片） | cherry-pick (9c4b9e5) |
| #80 | `--tiered-experts` 三级专家源（VRAM 无内存副本 / pinned 预算 / SSD 冷层） | cherry-pick (1a4d2b6) + 冲突解决 |
| #130 | setup 接受 7.x 卡（保留了 #87 的 7.5 门槛文案） | cherry-pick (a670b95) |
| #134 | RAM 检查改为计算式（专家 arena + 13.7KB/token KV + 余量） | cherry-pick (573fb86) |

## 我们的新增改动

### 1. TieredExpertSource 的 Windows 实现（M1）

原 PR #80 在 Windows 只留 stub。实现在 `src/core/tiered_source.cpp` 的 `_WIN32` 分支：

- **文件映射**：`VirtualAlloc(MEM_RESERVE, PAGE_NOACCESS)` 预留 `file + max_blob` 地址空间 →
  `MapViewOfFileEx` 把文件视图放在预留区起点。尾部保持 NOACCESS（Linux 语义是零页，
  但 blob 读取按构造不越过文件末尾；若越界，SEH 崩溃即诚实报告）。
- **PINNED 层 = 独立 `cudaHostAlloc` 区**：NT 内核无法对文件映射做 MAP_FIXED 原地换页，
  所以 pinned 专家放在独立 arena，`blob()` 按 tier 表分派（每路由专家一次分支 + 一次寻址，
  对 1.4MB 的 blob 读取可忽略）。`cudaHostAlloc(Portable|Mapped)` 天然 pinned，
  无需 cudaHostRegister / run 合并 / bounce-buffer（`expert_cache.cpp` 的 bounce_copy 仅在
  注册区间越界时触发，本方案不会发生）。偏移记录在 `pin_off_`。
- **MADV_DONTNEED 无等价物**：VRAM 层的文件页自然落入 standby 列表——Windows 把 standby
  计入"可用内存"，语义与 Linux 的 MemAvailable 一致。`settle` 不做显式丢弃。
- **预取** = `PrefetchVirtualMemory`（SDK 26100 起是 4 参数，第 4 参 Flags 传 0）；
  流式读 = `FILE_FLAG_NO_BUFFERING` 第二句柄 + OVERLAPPED 定位读 + 4K 对齐 bounce 缓冲
  （`STRATA_NO_DIRECT_STREAM` 同上游语义）。
- **预算** = `GlobalMemoryStatusEx.ullAvailPhys - reserve`（standby 计入可用）。
- **env 旋钮与上游一致**：`STRATA_NO_DIRECT_STREAM` / `STRATA_NO_COLD_PREFETCH` / `STRATA_SYNC_PREFETCH`。

### 2. 构建注意事项（Windows + 便携 CUDA）

- 工具链：VS2022 BuildTools (MSVC 19.44) + Ninja + **便携 CUDA 12.4**（`E:\strata-setup\cuda-portable`，
  由官方安装包解包合并而成，无注册表/驱动改动；nvcc 直接经 `-DCMAKE_CUDA_COMPILER` 指定）。
- `-DCMAKE_CUDA_FLAGS="-allow-unsupported-compiler"`：CUDA 12.4 官方支持上限低于 MSVC 19.44，实测无碍。
- **`-DCMAKE_CUDA_RUNTIME_LIBRARY=Shared` 必须设置**：CMake 默认追加 `cudart_static.lib`，
  与 Strata 显式链接的动态 `cudart.lib` 在 Windows link.exe 下多重定义（Linux 的 ELF 不报）。
- 运行时 `PATH` 需含 `cuda-portable\bin`（cudart64_12.dll、cublas64_12.dll 等）。
- 已知上游问题在 Windows 放大：LLFSE/MSVC 把大 ifstream 读切成 4KB（#89 已修）；
  大块 pin 需要足够页面文件（#141）——固定页面文件建议 ≥16GB。

### 3. CJK / MTP 修复（Issue #137 的运维版）

随包 `draft_vocab.bin` 只有 27/40525 个 CJK token → 中文草稿验收崩盘（#137 实测：绕过它
中文 +14%，76.8→87.7 tok/s）。引擎在 `rt/` 缺 `draft_vocab.bin` 时自动回退完整原生 draft head
（`mtp.cpp` L302 的 `if (dhead_ == nullptr)` 路径，L467 `sub ? dhead_ : head_->weights()`）。
**因此本 fork 的 MTP 安装步骤不部署 draft_vocab.bin。** 上游 PR 候选：多语种 draft 词表生成。

### 4. 验证状态

- 12 个 parity 测试在 sm_75 通过（bf16_gemv/gdn/gr/kv_q4/kv_q8/kv_stream/s_gemv/elementwise/
  cvec/dequant_s2/sampler 全绿）。
- `iq_parity` 缺夹具（`tools/iq_fixture.py` 未随源码发布）→ 推迟到 M2 用真实权重做端到端
  贪婪解码对拍（CPU 侧专家本就是 ggml-cpu 原版内核，CUDA MMQ 仅服务预填充）。
- `strata-device.exe`：2080 Ti cc 7.5 识别正常，20K 上下文内存规划 FITS。
- 端到端 + tiered 实测：待 M2（模型下载后）。

### 5. 运行配置备忘（M2）

- `--kv q4_0`（bench：快 3.7%，质量近中性）
- `--ple-io direct`（默认；防止 Engram 表读驱逐冷专家页缓存）
- `--host-budget-gib` / `--host-reserve-gib`：10–14GiB 起扫（#80 作者建议）
- `--pcie-frac`：上游 #44 自动探测，验证即可
- `--spec 2` vs `4` 差异小（#137），默认 4


## 6. M2 首跑记录（2026-09-30）

- **机械目标达成**：完整端到端在 2080 Ti 22GB + 32GB + Windows 上运行：解码 38.2 tok/s（首跑冷启动）
  ～53.3 tok/s（无 MTP），三层驻留 VRAM 11221 (15.04 GiB) / PINNED 8901 (12 GiB) / COLD 4454 (5.98 GiB)，
  MTP 草稿 + 自适应层交换 + PLE direct I/O + PCIe 自动探针（3.1 GB/s → pcie_frac 0.00）全部工作。
- **AVX-512 缺失被优雅接住**：启动即走 AVX2 多 token i-quant 内核（#43）。
- **遗留正确性 bug**：贪婪解码输出恒为 token 0（"!"）——logits 疑似 NaN（argmax 遇 NaN 恒取首索引）。
  llama.cpp（CPU 金标准，同一 GGUF 同模板）输出连贯 → 权重/量化/分片无问题，是本引擎 sm_75 原生内核的数值 bug。
  二分进展：MTP 无辜；qsa 单独禁用无效；gr/gdn/bf16/indexer 被 fused verify window 冻结无法经旗标隔离
  （禁用即拒绝启动）；canonical 回退组合在生成阶段挂起。
- **调试基础设施**：`STRATA_DISABLE_NATIVE=gdn,qsa,router,...`（逗号分隔，按名禁用原生路径回退 canonical）
  已加入 generate.cpp；`tiered_test_win.exe` 单元测试（STRATA_TIERED_TEST=ON）。
- **下一步**：① 构建 v0.1.22 + #87（Adamyno 验证过的组合）+ Coder IQ1_M（23GB 塞得进 32GB）做版本二分；
  ② 或逐层 NaN 探针定位第一个产生 NaN 的层；③ llama.cpp logits 对照定位首个发散位置。
- **重要教训：分片 1（GGUF）是运行时必需**（--native 路径读其 BF16 稠密投影），打包完成后不可删除。
- 便携 CUDA 12.4 运行时与 560.94 驱动兼容良好；`CMAKE_CUDA_RUNTIME_LIBRARY=Shared` 必须（否则 Windows
  链接器多重定义冲突）。


## 7. 等待期工作与用户脚本（C:\strata-models\）

- `run-iq2xs.bat` 日常启动（serve 服务器，装载 2-4 分钟，浏览器 http://127.0.0.1:8080/ 或 chat.py）
- `probe.bat` + `analyze_layers.py` NaN 层定位探针（机器空闲时跑，--dump-layers 逐层残差转储）
- `bench-m2.py` 基准矩阵（中文×3 / 英文 / 代码×2，真实提示词测速）
- `first-run.bat` 直连引擎冒烟；`strata-iq2xs.json` 服务器配置（lib_dirs 指向便携 CUDA）
- Coder IQ1_M 分片 1（27.58GB）下载中：版本二分（0.1.22+#87 对照）与编码场景双用途；
  Coder 的 shard 2 与 IQ2_XS 完全相同（26.82GB Engram 表），无需重下
- **显存竞争注意**：用户占用显存时 prefill 8192-token 块放不下（"device buffers do not fit"），
  用 `--prefill 1024`；且两个引擎实例不能并存（第二个的 verify staging 分配失败）
- 首跑关键数据（用户占用机器时的保守值）：38.2-53.3 tok/s 解码、服务器实测 38-41 tok/s
  @ 命中率 96.5-100%、专家缓存 auto=11221 槽 (15.04 GiB)、settle 52.2s、TTFT ~19s（含装载）
