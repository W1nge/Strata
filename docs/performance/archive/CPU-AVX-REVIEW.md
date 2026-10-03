> 历史原始报告（归档于 2026-10-03）。本文的“当前/已启用/未推送”只表示当时状态；最终采用项、纠错和发布状态以 [总总结](../OPTIMIZATION-SUMMARY.md) 为准。本归档仅添加此说明并替换个人工作区路径，未改写测量结论。附件名可能指本机证据包；已公开的小型数据见 [索引](../../../bench/results/2026-10-03-local-optimization/README.md)。

> 历史阶段记录：其中的 PCIe x4 数据不代表当前 x16 配置；最新结论见 CONTINUOUS-OPTIMIZATION-X16.md。

# Strata CPU / AVX 技术复核

2026-10-02。审查对象：`C:/strata-models/EXPERT-REVIEW.md`，以及本机 Strata checkout `e287ed08abb8468f0f6250d31813fd73eb745f2f`。此次只在 Codex 工作目录中构建独立探针；未修改引擎、模型包、启动配置或系统设置，未重跑完整模型 benchmark。

**核心结论：CPU 路径重要，但现有材料不能证明已经达到 AVX2 平台的软件极限。文档把“已有多 token 内核”进一步解释为“已经使用 AVX-VNNI”，这一点与当前源码、目标文件反汇编不符。实际存在一个已经测出局部收益的 AVX-VNNI 优化入口。**

**1. 指令集能力和实际使用情况**

“AVX3”需要按具体语境区分；若指 AVX-512，本文使用正式名称 AVX-512。AVX-VNNI 是可以使用 256 位向量的整数点积扩展，不以支持 AVX-512 为前提。

本次 CPUID 探针对当前进程可用的全部 28 个逻辑 CPU 逐一绑定测试：

| 项目 | 本机结果 |
|---|---|
| 可用逻辑 CPU 掩码 | `0x0fffffff` |
| AVX2 支持掩码 | `0x0fffffff` |
| AVX-VNNI 支持掩码 | `0x0fffffff` |
| AVX512F 支持掩码 | `0x0` |
| XCR0 | `0x7` |

CPU 品牌字符串返回 `Genuine Intel(R) 0000`，所以此次探针独立确认的是功能位，不是零售型号；i7-13850HX 型号来自用户文档。额外用 CPUID leaf 0x1A 验证了基准测试中的逻辑 CPU 0 为 P 核（0x40）、逻辑 CPU 16 为 E 核（0x20）。

当前 native Q2_0 down 的实际调用链：

```text
ExpertPool::run_split_multi_native
  → run_phase(6)
  → ExpertPool::drain 中 nfmt_->d_type == 42
  → q2_rows_any
  → cpu_avx512_ok() == false
  → q2_0_gguf_rows_multi_avx2
  → q2_avx2.cpp 的 row_multi
```

这里使用 `vpmaddubsw + vpmaddwd`。`s2_expert_down_rows_multi` 在另一条 canonical 路径，不能作为当前 native 包已经使用 VNNI 的证据。

现有目标文件反汇编结果：

| 目标文件 | vpdpbusd 静态出现次数 | vpmaddubsw | vpmaddwd |
|---|---:|---:|---:|
| q2_avx2.cpp.obj | 0 | 40 | 40 |
| iq_avx2.cpp.obj | 0 | 190 | 190 |

这些是展开后的静态指令计数，不是运行时执行次数。实际 `build.ninja` 也显示这两个源文件按 `/arch:AVX2` 构建；ggml x86 quants 的命令行没有启用 AVX-VNNI。不能仅凭 CMakeCache 中 GGML_AVX2=OFF 等条目判定 ggml 没开 AVX2，实际命令行有 AVX2 定义及编译选项。

建议新增独立的 AVX-VNNI 分派，不要把整个工程切到 `/arch:AVX512`。本机编译器提供 `_mm256_dpbusd_avx_epi32`，测试确认它生成 VEX 编码的 `vpdpbusd`，可在本机运行。保留普通 AVX2 回退，运行时检查 AVX/OSXSAVE、XCR0 的 XMM/YMM 状态、AVX2 和 CPUID(7,1).EAX[4]。仅修改 ggml 的配置也不会自动改写 Strata 自有的这两个内核。

**2. 已实测的 Q2_0 AVX-VNNI 小基准**

实验在工作目录中复制 `q2_avx2.cpp`，保持权重解包、激活量化、缩放、浮点累加和多 token 分块不变，只将两个 `maddubs + madd` 点积换为 `_mm256_dpbusd_avx_epi32(zero, weights, activations)`，另改导出函数名避免冲突。

数据是 IQ3 原生包第 1 层、expert 0 的完整 Q2_0 down 矩阵：2560 行 × 640 列，460800 字节。权重来自真实 experts.bin；激活为固定随机种子产生、再经现有 `act_quant_q8_1_avx2` 量化的合成激活，并非模型运行时捕获的激活。

正确性：NT=1～8，共 92160 个输出，与原内核逐值完全一致，全部有限。该替换的整数中间结果也不会触发原 `maddubs` 的饱和：Q2 码值 0～3、激活 -127～127，两个乘积之和的绝对值最多为 762。此测试不等于完整模型的质量回归。

性能方法：单线程固定在指定核心，一份矩阵反复运行，数据主要在缓存内。一次预热，7 组交替先后顺序的配对测量，每组每实现调用 64 次；表中为单次调用耗时中位数，速度比为原耗时/新耗时。

| 核心 | 同一专家的 token 数 | AVX2，µs | AVX-VNNI，µs | 速度比 |
|---|---:|---:|---:|---:|
| P | 1 | 61.681 | 57.630 | 1.070× |
| P | 2 | 92.750 | 84.225 | 1.101× |
| P | 4 | 153.744 | 136.458 | 1.127× |
| P | 8 | 308.084 | 273.275 | 1.127× |
| E | 1 | 127.798 | 122.761 | 1.041× |
| E | 2 | 214.613 | 194.553 | 1.103× |
| E | 4 | 424.414 | 338.753 | 1.253× |
| E | 8 | 849.839 | 683.188 | 1.244× |

这是局部优化的正证据，不能直接换算为整机 tok/s。多核并发、功耗、专家分片大小、缓存状态和实际每专家 NT 分布都会改变收益；spec=4 也不代表每个 miss 专家都恰好有 NT=4。

若仅举例假设整轮 150ms、其中可被此优化覆盖的 down 时间为 20ms、该部分加速 20%，整轮会从 150ms 变为 146.67ms，吞吐约增加 2.3%。这解释了为何值得修，但不能承诺弥合 18 与 60 tok/s 的差距。这些 150/20ms 是说明计算方法的假设，非此次端到端测量。

**3. “6.9 GB/s 证明 AVX2 计算受限”证据不足**

当前打印公式为：

```text
pool.multi_bytes / (pool.ms_multi_gu + pool.ms_multi_down)
```

native 路径的分子累计 `n * f.bytes`，每个被处理的 distinct 专家按压缩 blob 大小计一次；分母围绕整个 `run_phase` 计时，其中含线程发布、等待完成和等待 worker 重新停驻。它不是内存控制器计数器读取的 DRAM 带宽，也不是纯 SIMD 指令执行时间。

实际还会有激活读取、码本查表、缓存命中/未命中、nt>4 重读、临时数据、调度与同步；这些都没有以相同口径计入分子。低于顺序内存带宽只说明没有展现出顺序流式带宽，不能排除访存延迟、缓存和并行度问题。

50W→200W 后的明显提升支持“CPU 频率/功耗敏感的工作很重要”。它仍不能单独区分整数点积、码本解码、前端/执行端口、缓存延迟或调度开销。不能据此断言双通道/Gear 2 无关，也不建议在没有相应证据时先改 BIOS。

建议将原结论改为：

> CPU 专家路径对当前性能有显著影响；功耗实验提示频率敏感开销较重。现有逻辑行吞吐不能唯一定位到 AVX2 算术吞吐，亦不能证明内核优化空间已尽。

**4. 除了 Q2 VNNI，优先核查的两个入口**

- **Gate/up 的真实热点与 NT 分布。** 当前 `native_gu_rows` 只有在 `nt >= 2` 且类型受支持时才进入自有多 token 内核；NT=1 和 IQ1_M 等类型走 ggml。需要按量化类型、NT、P/E 核记录时间/任务量，避免优化没有覆盖主耗时的代码。检查 NT=1 的分派是否仍最适合这台机器，而不是沿用别的硬件上的注释结论。
- **IQ 解码和多 token 寄存器压力。** IQ 内循环的 `madd_epi16(..., sc)` 同时应用子块缩放，不能机械地把三条指令全替换成一个 `vpdpbusd`。应分开评估码本读取、符号展开、缩放和点积。AVX2 只有 16 个 YMM 寄存器，较大 NT 的多个整数/浮点累加器可能产生栈溢出保存；这是待反汇编/基准确认的候选，不是已证明的主要瓶颈。可先对真实热点比较 NT 分块、行分块或紧凑预排布，再考虑膨胀权重存储的解码缓存。

线程池的 `run_phase` 前后仍有 `wait_parked` / `wait_done`。已有 P-only 实验支持保留 E 核，但不等于最后一个分片的尾延迟或固定 `3 * threads` 分片粒度已经最优。只有计时显示同步/尾部明显，才值得调整分片；不应重复已排除的盲目加线程实验。

**5. AVX-512 对照不能按标签解释**

AVX-512 是一组扩展，不等于“256 位换成 512 位所以整体两倍”。当前 Strata 自有 AVX-512 分派要求 F、BW、VL、VNNI、VBMI 同时满足。若上游对照 CPU 确为 Skylake-X，它不具备后两项，不能直接推断对照运行了这里的现代 AVX-512 专家内核。它仍可能使用 ggml 的其他 AVX-512 路径；准确解释需要对照机器的 CPUID、实际内核、线程数和路由/缓存配置。

本机 17.4/25.4 tok/s 可以是合理结果，但现有不同机器、不同上下文与负载的对比无法证明已到上限，也无法承诺通过某个开关达到 45～60 tok/s。

**6. 旧 Q2_0 全零现象已获得直接复现**

探针链接当前 Strata 构建中的 ggml-cpu.lib 和 ggml-base.lib，在同一进程以相同权重、相同输入调用同一 traits 点积路径，初始化前后比较：

```text
before ggml_cpu_init(): f16_table[2.0] = 0.000000, dot = 0.000000
after  ggml_cpu_init(): f16_table[2.0] = 2.000000, dot = 12803.187500
```

源码对应 `ggml-cpu/simd-mappings.h` 的 FP16 查表及 `ggml-cpu.c` 中的初始化。因而“未初始化 FP16 表会让这个 Q2_0 探针返回零”已实证。历史二进制未重新构建，所以它不能证明旧运行的全部环境细节；也不能用这个结论解释另一个 IQ1_M SEGV 或旧包的尺寸 bug。

**建议顺序**：先将上述文档归因更正；随后把已经通过局部对拍的 Q2 AVX-VNNI 候选接入实际 `q2_rows_any` 分派，做完整模型正确性及端到端 A/B；更大优化的方向由 gate/up 类型、NT 和阶段计时决定。不要再在 native_down_rows 里增加 Q2 分支，也不要因“硬件支持 VNNI”而假定软件已经使用。

**证据索引与复现**

Strata 源码根目录：`<REPO>`。

| 位置 | 证据 |
|---|---|
| src/kernels/cpu/pool.cpp:392 | native Q2 down 调用 q2_rows_any |
| src/kernels/cpu/pool.cpp:420 | s2 函数位于另一分支 |
| src/kernels/cpu/expert_layout.cpp:22 | AVX-512 功能位检查 |
| src/kernels/cpu/expert_layout.cpp:54 | Q2 的实际 AVX2/AVX-512 分派 |
| src/kernels/cpu/q2_avx2.cpp:50 | 两个普通 AVX2 点积 |
| src/kernels/cpu/iq_avx2.cpp:178 | 含子块缩放的 IQ 点积 |
| src/kernels/cpu/native_expert.cpp:87 | 多 token 快路径进入条件 |
| src/kernels/cpu/pool.cpp:429 | phase 包含线程池等待 |
| src/kernels/cpu/pool.cpp:496 | native 阶段计时与字节累计 |
| src/program/generate.cpp:4908 | 逻辑行吞吐打印公式 |
| CMakeLists.txt:485、541 | 各源文件编译 ISA 设置 |

附带 `cpu-review-repro.zip` 包含探针源文件、独立 VNNI 候选、构建批处理及原始日志。需在具备相同本机目录和模型包的环境中解压，在解压目录运行批处理。基准中的 VNNI 候选没有产品级运行时回退，仅用于本次已确认 AVX-VNNI 支持的机器；不要直接发布为兼容所有 AVX2 CPU 的实现。
