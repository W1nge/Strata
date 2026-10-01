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


## 8. 版本二分准备（0.1.22 对照树）

- `../Strata-bisect-0122`（worktree @ 6a772da + cherry-pick #87），分支 `bisect-0122-turing`，sm_75 构建成功。
- **发现**：0.1.22 的 `qsa_prompt_attn.cu` 用裸 cp.async/m16n8k16，sm_75 编译失败（PR #87 从未编译过 0.1.22，
  Adamyno 的端到端是 0.1.20）。已在对照树加构建期守卫 `STRATA_NO_SM80_QSA_PROMPT`（经 CMAKE_CUDA_FLAGS 传入，
  sm_75 分支回退解码注意力内核）。守卫曾把 #if 方向写反（#ifdef→应为 #ifndef），已修。
- **主线 0.1.24 无此问题**：上游已给 qsa_prompt_attn 加了 `STRATA_PA_SM80` 宏 + 运行时 cc_major 门控
  （"compile them to a trap; qsa_prompt_attn_batch refuses such a device"）→ **预填充注意力路径正式无罪**。
- NaN 嫌疑收窄至：{gdn native, bf16 投影, indexer} 的 fused verify window 组合，或更深的调度问题。
- Coder IQ1_M 分片 1 下载完成后：0.1.22 对照引擎用经典 arena（23.4GB）跑 Coder 做正确性对照。


## 9. NaN 根因与修复（2026-10-01，重大突破；同日晚间复核修正结论）

### 9.1 当时的结论（**部分作废**，保留原记录）

**根因链（当时认为全部实证）**：
1. GSQ-RCO IQ2_XS 发布的层 8/13/37 gate/up 为 IQ1_M，且全部 48 层 down 为 Q2_0。
2. ~~ggml-cpu 的 x86/MSVC 内核对这两个类型是坏的~~（**见 9.2 复核：Q2_0 内核其实是好的**）。
3. llama.cpp 自身（含 dequant+scalar dot）读同一 GGUF 正常 → 权重无辜。
4. 0.1.22 与 0.1.24 同病 → 非版本回归。

### 9.2 复核（2026-10-01 深夜）：内核从未坏，坏的是当时的探针

- 重写的手工块测试（`tools/test_q2_0.cpp`，**先调 `ggml_cpu_init()`**，走引擎同款 traits 表路径，
  并带 Q4_0 对照组）：Q2_0 得 12803/期望 12800（偏差=激活量化舍入），Q4_0 对照同过。
  旧探针 0.0 全零的极大概率成因：**没调 ggml_cpu_init()，fp16 查找表全零 → 缩放 d 读成 0**。
- 真实块双端验证（`tools/rowprobe.cpp` + `tools/probe_check.py`）：从原生包 experts.bin 取全部 8 种类型
  的真实数据行（gate/up/down × 首尾行，48 层 × 6 探针 = 288 个），ggml-cpu vec_dot 值 vs
  gguf-py/requant_gsq 反量化基准，**0 失败，最大误差 = 量化误差上界的 0.117**。
- GPU 侧 Q2_0 内核（dq_q2_0 / Fmt<42> / MMQ q2_0 实例）逐行读码核对，语义与 llama.cpp 一致；
  needle 8K/32K × 3 深度全中 → 长上下文 prefill（含 GPU Q2_0 MMQ）无恙。
- **教训**：手造块测试必须先 `ggml_cpu_init()`；单探针结论必须再用独立路径（真实块 + 反量化基准）复核
  才能作为工程决策依据。requant 的尺寸代价（IQ2 +33% / IQ3 +11%）原本可以不付。

### 9.3 修复与现状

- **当时真正治好 NaN 的是同批修复的打包逐专家尺寸 bug（per-row → per-expert）+ 升位包 + GPU case 补齐**；
  Q2_0 CPU 内核自始至终是好的。
- requant 机制保留：含 IQ1_M 的包（IQ2_XS 发布的层 8/13/37、Coder）仍需升位——x86 iq1_m 的 SIMD 内核
  读 repack 过的 scales，原生 raw 块在该路径未验证。`STRATA_NO_REQUANT=1` 让 iq_pack 按发布版原类型
  打包（IQ3_XXS 发布即用此模式）；默认维持 requant 行为。
- 原生 IQ3_XXS 包成为新主线（见 §10）。

## 10. 性能优化日志（2026-10-01，原生包 + 画像重建）

1. **Q4_0/Q8_0 进 MMQ**（`src/prefill/moe_mmq.cu` 两个 switch + `CMakeLists.txt` 的
   `template-instances` 列表加 q4_0/q8_0）：requant 层的 prefill 从 f16 GEMM 回退切回 int8 MMQ。
2. **原生 IQ3_XXS 包转正**（`STRATA_NO_REQUANT=1` 打包，42.8 GiB）：显存层 7704 → **8981 专家（+17%）**，
   同预算下命中率直接受益。启动配置 `strata-iq3xxs-native.json` / `run-iq3xxs-native.bat`。
3. **画像重建**：`tools/make_profile.py` 加 `--trace-first`（基础画像覆盖全部 24576 对时，原合并逻辑
   无法重排——轨迹永远"补充"不"改序"）。服务器模式 `--dump-routing` 累积 11 个部署形态请求
   （真实代码文件上下文 + 中文写作 + 多轮，`C:\strata-models\trace_workload.py`）→
   `expert-profile-user.bin`。**expert cache 命中率 58.4% → 平均 75.6%（峰值 93.8%）**。
4. **测速**（2080 Ti 22G / DDR4-4000 双通道 / AVX2，机器空闲）：bench 六提示词平均
   **10.1 → 11.8 tok/s**（中文对话类 9.7-11.9 → 14.0-14.9）；冒烟 40-token 贪心 decode
   **5.78 → 10.60 tok/s**；32K prefill ~344 tok/s；needle 6/6。
   CPU i-quant 吞吐 ~3.5 GB/s 是 AVX2 算力受限（计算瓶颈，不是内存带宽），AVX-512 机型不可直接比。
5. 待办：MTP min-p/spec 扫描、`--host-budget-gib` 扫描、Q2（原生 35.5 GiB 版）需先验证 iq1_m raw 块。

## 11. Prefill 调优记录（2026-10-01 晚）

31K token 提示的分阶段测量（`--tokens-file` + `tools/bpe_encode.py` 生成）：

- 基线（`--prefill 8192`，4 chunks）：核心 90.6s（342 tok/s）；**专家流式 71,408 次，主机侧 37.3s（41%）**
  ——每个 chunk 把 pinned+冷层 ~1.78 万专家全部重流，跨 chunk 复用为零。
- **`--prefill 16384`（2 chunks）：核心 74.7s（415 tok/s，+21%）**，流式降到 39.8K 次 → 已固化为默认。
  32768 反而劣化（PLE 上传 9.7s + 墙钟 124s）。
- 已排除的假设：`--pcie-frac 0.55`（prefill 的 DMA 决策独立于它，两跑完全相同）、
  `STRATA_STAGER_THREADS=32`（stager 非瓶颈，16K 下还略差）。
- 剩余瓶颈：冷层页入 ~2GB/s（47.6GB/31K 提示）。层间路由依赖（L+1 的路由要等 L 的输出）决定了
  页入本身就在关键路径上，双缓冲的上限被它锁住；再往上需要冷层读并行深度的内核级改造，
  收益估计 +20-30%，列为后续项。
- `--stage-timing` 的使用限制：需要 `--no-capture`，而 `--no-pool` 地板测量会以 100% GPU 空转挂死
  （native pack 31K 提示实测）——别用。
- profile v2：两轮共 27 个部署形态请求（含 4.3K token 代码上下文）合并重建
  （20,912 热对 + 3,664 基础补齐）；bench 均值与 v1 持平（11.6 vs 11.8，噪声内），
  长代码上下文覆盖率提升。bench 的 Fibonacci/SQL 类提示不在语料中，命中维持 ~60% 属预期。

## 12. iq1_m 复核与 IQ2 速度档（2026-10-02）

- **iq1_m 的"SEGV/需 repack"结论一并撤回**：真实块验证（`tools/test_iq1m.cpp`，IQ2_XS 发布层 8 gate
  expert0 row0，560B）——canonical 与 `_generic` 内核同值（-1.22456），对 requant_gsq 反量化基准
  ratio 0.017，PASS。本构建里 canonical iq1_m 就是 raw-block 路径（arch-fallback 把 _generic 编译为正名）。
- **原生 IQ2_XS 速度档**（`STRATA_NO_REQUANT=1`，experts.bin 33.02 GiB）：显存层 **10,287 专家（13.78 GiB）**
  vs IQ3 档 8,978；CPU pool 64.8 ms/轮（8.7 GB/s），命中率 ~85%（冒烟提示）。
  **bench 平均 18.8 tok/s（IQ3 档 11.6 的 +62%）；40-token 贪心 decode 19.24 tok/s（+43%）**。
  启动配置 `strata-iq2xs-native.json` / `run-iq2xs-native.bat`。质量为 2-bit 档（长文/代码可用，精细推理让位）。
- 显存 auto 尺寸收缩的坑（`generate.cpp` shrink 级联）：IQ2 包的 auto 规划 10,689 槽在写入后 0 MiB free，
  两次 `bytes/4` 收缩 + 反复开关分配耗尽 Windows commit → verify 的 cudaHostAlloc(Mapped) 失败。
  显式 `--expert-cache 9800` 绕开；同一配置重跑即恢复（临时性 commit 压力）。engine 侧的 auto 余量
  修正（free 读数偏高 ~1GB 的 WDDM 问题）列为后续项。
- **AVX2 gate/up 内核评估**：`iq_avx2.cpp` 已是精心调优的设计（码本查表每 32 值块一次、keven_signs
  预计算表、多 token 摊销），无低垂果实；再往上需要 VTune 级微架构工作。

## 13. CPU 功耗解锁重测（2026-10-02）：13850HX 50W → 200W

CPU 是 AVX2 i-quant 内核的算力瓶颈（§10 的结论），解锁功耗直接兑现。同一方法同机重测：

| 指标 | 50W | 200W | Δ |
|---|---|---|---|
| IQ3 bench 平均 | 11.6 | **17.4** | +50% |
| IQ3 40-token 贪心 decode | 13.45 | **15.69** | +17% |
| IQ3 pool 行吞吐 | 3.5 GB/s | **6.9 GB/s** | ×2.0 |
| IQ3 31K prefill 核心 | 415 tok/s | **634.8 tok/s** | +53% |
| IQ2 bench 平均 | 18.8 | **25.4** | +35% |
| IQ2 40-token 贪心 decode | 19.24 | **23.00** | +20% |
| IQ2 pool 行吞吐 | 8.7 GB/s | 9.1 GB/s | +5%（已接近纯搬运上限） |

IQ3 的 MTP 验收率在 200W 下到 0.96（draft 生成更快 → draft 与 verify 的时间比更优）。
prefill 主机侧流式 37.3s → 22.7s（CPU 解锁同时加速了拷贝/调度）。
结论：解码的下一个墙回到"命中率 × 内核常数"，prefill 回到"冷层页入"；功耗墙不再是第一约束。

## 14. MTP 压榨分析（2026-10-02）

**与源项目的对比澄清**：上游 2080Ti 测试者的 MTP 数据是验收 ~0.73、CJK 修复后中文 76.8→87.7 tok/s
（**相对收益 +14%**）。我们（IQ3 档 200W）关 MTP 约 ~10 tok/s（1 token/轮 × ~100ms 池）→ 开 MTP 18.6
= **相对收益 +80-90%**。绝对速度差（87.7 vs 18.6）是硬件账（AVX-512 vs AVX2、多通道 vs 双通道），
不是 MTP 机制差距——MTP 的收益本质是"verify 窗口摊销串行成本"，上游瓶颈在 GPU 侧（窗口成本高、
收益小），我们的瓶颈在 CPU 池（串行小批、摊销极有效），所以我们的 MTP 相对收益反而远超上游。

**本次扫描（IQ3 档 200W，40-token 贪心）**：
| spec | min-p | 验收 | tok/轮 | decode |
|---|---|---|---|---|
| 4 | 0.3 | 0.794 | 3.08 | 17.70 |
| 4 | **0.4** | 0.897 | 2.86 | **18.57** |
| 4 | 0.5 | 0.893 | 2.67 | 17.69 |
| 4 | 0.6（旧默认） | 0.96 | 2.50 | 15.69 |
| 6 | 0.4 | 0.725 | 3.42 | 17.26 |
| 6 | 0.3 | 0.769 | 3.73 | 8.68（suffix-drafts 路径触发，禁用） |

- 50W 时代定的 min-p 0.6 在 200W 下过时：CPU 变快 → verify 边际成本降 → 更激进的提议（低 min-p）
  净赚。min-p 0.4 固化进两档配置（bench 均值持平 17.1 vs 17.4，噪声内；smoke 类提示 +18%）。
- spec 6 增加 tok/轮（3.4-3.7）但不增加 decode：verify 窗口变大、池更贵；spec 6 + min-p 0.3 触发
  suffix-drafts 路径严重劣化（8.68）——禁用组合。
- 高验收率（0.96）≠ 高速度：min-p 高 → 提议少 → 验收虚高但 tok/轮低。优化目标是
  tok/轮 × 轮速，不是验收率。

## 15. "CPU 优化"排查补记（2026-10-02）

- 尝试为 Q2_0 down 写多 token AVX2 内核（native_down_rows 分派）：奇偶校验通过后，端到端 A/B
  **零差异**（down 20.8 vs 20.5 ms/轮）。后续源码与反汇编复核更正：native 池实际走
  `q2_rows_any` → `q2_0_gguf_rows_multi_avx2`，已有多 token 摊销，但没有 AVX-VNNI；
  `native_down_rows` 的 Q2_0 分支对 pool miss 不可达。已撤销的死代码不能排除 AVX-VNNI 收益（见 §17）。
  其他可继续评估的杠杆：
  ① **v2 混合量化**（冷专家 IQ2 化：miss 字节 -30% → decode 约 +12%，需引擎支持按专家混合类型）；
  ② profile 语料继续扩（+3-5%/轮）。
- 池内核对混合 P/E 核已有物理核绑定与多 token 摊销；这不等于已用尽 CPU 软件优化空间。
  后续实测确认了 Q2_0 AVX-VNNI 的局部收益（§17）。

## 16. 社区经验与 P 核亲和实验（2026-10-02）

社区检索（AVX2-only 推理的经验）三条线索：
1. **ik_llama.cpp**（github.com/ikawrakow/ik_llama.cpp）：手写 SIMD 内核（AVX2/AVX-512/VNNI）+ 重设计的
   IQ2/IQ3 量化类型（iq2_ks 等），CPU+GPU 混合跑 MoE（DeepSeek/Qwen3）有 5× 提速报告——**内核技法的
   移植来源，最值得深挖**。
2. **Intel 混合架构 E 核毒化**（llama.cpp discussion #572 等）：P 核-only 最快三倍——但那是
   "每算子全线程硬屏障"的结构；**本引擎实测不成立**（见下）。
3. **BitNet.cpp 的 TL/I2_S LUT 内核**（arxiv 2502.11880）：激活也低比特化后用 PSHUFB 查表做 2-bit
   乘加，绕过解包税——需要激活量化重构，列未来方向。

**P 核亲和实验**：13850HX = 8P(16线程) + 12E（逻辑 CPU 0-15 为 P）。池现设计 19 worker = 全部物理核
各一（host 占第一个 P 核）。流程亲和掩码 0xFFFF（P-only）测试：
- 先踩坑：引擎建 worker 时**无视进程亲和掩码**，19 个 worker 被钉到掩码外的核上 → 调度崩坏
  （1.87 tok/s）。已修：`pool.cpp` 的 `physical_cores()` 现在按 `GetProcessAffinityMask` 过滤
  （正确性修复，保留）。
- 修正后实测：P-only 池（7 worker）**16.41 tok/s** vs 混合池（19 worker）17.6-17.9 —— **慢约 7%，
  E 核毒化理论在本引擎被否决**：per-layer 动态队列下 E 核做的是有效功，丢 12 个 worker 的损失
  大于屏障平滑的收益。与 llama.cpp 的差异在屏障结构（他们是算子级全线程同步）。
- 每 worker 吞吐：P 核 ~1.1 GB/s，E 核 ~0.46（2.4 倍比），与拓扑预期一致。

## 17. Native Q2_0 的 AVX-VNNI 分派（2026-10-02）

- 当前机器的 28 个逻辑 CPU 均报告 AVX2 + AVX-VNNI，无 AVX512F。旧 `q2_avx2.cpp.obj` 和
  `iq_avx2.cpp.obj` 均没有 `vpdpbusd`，不能把硬件支持当成软件已经使用。
- 增加独立 `q2_avx_vnni.cpp`，以 VEX 编码的 256-bit `vpdpbusd` 替代 Q2 的
  `maddubs + madd`。与 AVX2 共用解包、缩放和 NT 分块实现，浮点累加顺序不变。
  编译器能力检测失败时不构建该实现；运行时检查 CPUID 和 OS YMM 状态。
  AVX-512 路径优先级不变。新路径暂由 `STRATA_Q2_AVX_VNNI=1` 显式开启；
  `STRATA_NO_AVX_VNNI=1` 或 `STRATA_FORCE_AVX2=1` 可禁用新路径。
  启动日志明确显示 native Q2_0 实际选择的 ISA。
- 独立真实权重微基准：IQ3 原生包 layer 1 / expert 0 / Q2_0 down，合成量化激活，
  NT=1..8 共 92,160 个输出与原 AVX2 完全一致。缓存内单核 NT=4 时，P 核 153.74→136.46µs
  （1.127×），E 核 424.41→338.75µs（1.253×）。这些不是端到端 tok/s 收益。
- 新增 `STRATA_Q2_VNNI_TEST=ON`，可独立构建 `q2_vnni_test`；CTest 覆盖启用、默认关闭和两种禁用开关。
  包含 NT=1..8、1/10/40 个块、非对齐行、子行区间、零/负缩放、极端及变化的整数激活，
  与 AVX2 精确比较，并检查未请求的 token/行不被写入。
- 复核归因：`pool multi` 的 GB/s 是逻辑压缩权重字节 / 整个线程池阶段耗时，不是实测 DRAM 带宽。
  功耗敏感支持 CPU 路径重要，但不能据此排除缓存、访存延迟、页入和同步，也不能证明 AVX2 已到极限。
- 旧 Q2_0 探针的初始化假说已在当前 ggml 库直接复现：`ggml_cpu_init()` 前表值为零、点积为零；
  初始化后 FP16 2.0 的表值为 2.0、点积 12803.1875。这不同时解释历史 IQ1_M 崩溃。
- 端到端试验（六提示词、每题最多 128 token、三轮，共每组 18 请求）：初始驻留服务 AVX2/13 GiB
  平均 wall 10.22 tok/s；AVX2/10 GiB 20.80；VNNI/10 GiB 16.74；VNNI/8 GiB 20.48。
  冷热缓存、页入和自适应驻留造成显著波动，不能宣称 VNNI 获得整机加速，也不能把配置差异写成
  已证明的 2× 提升。因此 VNNI 暂保持 opt-in，本机日常 IQ3 配置仅将 pinned budget 从 13 改为 10 GiB。
- 最终默认配置检查：四项 CPU CTest 全过；Paris 冒烟正确；生成 Fibonacci 函数的五组输入全过；
  needle 的 10/50/90% 深度，在实际约 4.8K 和 16K 上下文中 6/6 通过。Windows 可用内存仍可能很低，
  冷启动/新主题仍有停顿，不能把全部延迟归因到 AVX2。

## 18. Windows 冗余映射页与固定专家驻留（2026-10-02）

- `begin_layer` 原来只对启动时的 kVram 专家查询实时驻留表；原先 kCold、后来提升到 GPU 的专家
  仍被预取，同一 verify 窗口的重复专家也重复排队。Windows/Linux 两条路径现均按实时驻留表过滤，
  并在本次调用中去重。GPU 逐出的专家仍会恢复 CPU 预取。
- 撤回 Windows “无法移出映射页工作集”的注释。微软明确规定：`VirtualUnlock` 用于未锁定页时，
  会移出工作集，并返回 FALSE/ERROR_NOT_LOCKED；映射本身仍有效，文件内容不变。
  https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualunlock
  启动时在 GPU 副本完成后移出 VRAM 专家的文件页，复制进 pinned arena 后移出相应文件副本；
  运行期在 CUDA event 确认自适应 H2D 完成后、以及 prefill 借用槽位回填同步完成后提示释放文件副本。
  范围向内按页对齐，避免影响
  相邻冷专家的边界页；不对 pinned arena 调用 VirtualUnlock。`STRATA_NO_VIEW_TRIM=1` 可禁用。
- Windows 回归测试覆盖：重复路由、冷专家提升/逐出、无效 ID、实际工作集驻留位变化，以及移出后
  重新读取字节完全一致。构建及测试通过。
- 独立 16 MiB 映射探针：4096 个驻留页 -> VirtualUnlock -> 0 个；重读内容一致。
  整机同为 10 GiB pinned：修复后加载完约 11.5 GiB 工作集、14.4 GiB 可用 RAM；不能将
  psutil 的大映射 RSS 数字直接当成完整驻留量，补用 64 位 QueryWorkingSetEx 抽样确认。
- `STRATA_DECODE_TIMING` 增加 gate/up、激活量化、down、adaptive join 和冷预取统计。
  动态交换时等待约 10–14 ms/window。采用同一个既有用户画像，关闭交换可减少 PCIe 传输并保留
  静态 GPU/pinned 分工；它在本机比追求更高的动态 GPU 命中率更快。
- 六提示词、temperature 0、reasoning none、每题最多 128 token、顺序三轮共 18 请求。
  指标为总生成 token / 总引擎 decode 秒数，包含第一轮；不是各请求速度的算术平均，也不含 prefill：
  AVX2/10 GiB 24.88；仅修预取 28.68；加映射页释放 35.24；再设 `--adapt-every 0` 为 **49.83 tok/s**
  （1419 token / 28.4759 s），三轮 37.03 / 60.20 / 60.28，含 prefill 的 HTTP 总速率 38.78 tok/s。
  Windows 文件缓存、试验次序和生成文本仍是混杂因素，不能把这些观测写成已证明的各项独立倍数收益。
- 日常 IQ3 配置保留 host budget 10、spec 4、spec-min-p 0.4，增加 `--adapt-every 0`；VNNI 仍默认关闭。
  不改变权重、量化档位、专家 top-k 或上下文上限。首轮及其他任务仍可能低于 40；49.83 是指定混合
  基准的汇总 decode 速度。全词表本来已在使用，上游 #137 的旧 CJK 词表缺失不适用于此部署。
  #137 的 76.8 -> 87.7 数据来自 RTX 5070 Ti / Ryzen 7700 / 96 GB，不能当成 2080 Ti/Skylake-X 对照。
- 补齐 prefill 回填后的文件页释放后，重启最终版本重跑原六题：**49.38 tok/s**，三轮
  36.11 / 60.44 / 60.52。随后六个新增题目（科学、历史、统计、数据库、Python 区间合并、物理），
  每题最多 256 token、三轮共 18 请求：**46.35 tok/s**，三轮 40.72 / 51.72 / 48.12。
  新题测试是已加载服务上的连续测试，不是清空 OS 缓存后的独立冷启动。此前长提示后换题的
  两轮试验只有 34.67（27.08 / 48.20），同样保留，不能把工作负载相关的改善写成最低速度保证。
- 最终构建复查：tiered-source 测试全过；Paris 冒烟与 Fibonacci 五个输入全过；4.8K/16K
  上下文、10/50/90% 深度的 needle 再次 6/6 通过。新题组输出达到上限时按 length 结束，未将其
  当成完整答案质量评测。36 次速度请求共 5875 token / 124.8743 s，汇总 47.047 tok/s。
