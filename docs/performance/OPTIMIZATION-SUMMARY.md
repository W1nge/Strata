# Strata 本机优化总总结：结果、全部尝试方向与当前版本

更新：2026-10-03。范围：本 fork 的 Windows/Turing 落地，以及 2026-09-30 至 2026-10-03 的 CPU、Decode、Prefill、缓存、256K 和社区方案验证。本文汇总现存报告与实验记录；更细的变体、样本和失败记录见文末归档。本文中的“已采用”指本机日常配置，**不代表所有实验开关都改成了源码默认开启**。

## 1. 当前结论

- 日常仍是 **单请求并发、32K 上下文、FP16 KV、原生 IQ3_XXS 模型**。MTP 使用保留中文和特殊 token 的 88,252 项草稿词表，目标模型的完整词表、专家 top-k 与权重保持不变。
- Decode 的“再提高 10%”目标已完成：14 题、三轮正式对照从 **60.407 → 67.131 tok/s，+11.13%**。这是该轮题集的聚合 Decode 速率，不含 Prefill，不是所有输入的保证；后续社区异步 commit 单独确认约 +0.91%。未将不同轮次涨幅累乘成总提升。
- Prefill 的主要已实现收益来自 **权重补回、流式 ring、Turing attention、首块 PLE 重叠及缓存复用**。长输入热态完整重读的 31K 已多次测到约 **35–36 秒**，进程首次长输入通常更慢且有长尾。最近一轮没有确认新的日常 31K 收益。
- 长窗口 Top-K 与 scorer key 复用已启用；最终组合关闭 HC BF16 候选。最终组合 128K 完整输入 **210.508 秒**，相比旧版两次中位数 219.749 秒少 **4.2%**，但最终组合只补测一次。**三项候选全开的 261K −15.4% 不是当前采用配置的成绩。**
- 空闲缓存已实现：最后一次生成结束后 **180 秒落盘、3600 秒过期删除**，模型常驻。它管理当前引擎共享状态，不按客户端对话分别计时，也不支持重启后恢复。
- 最大剩余 Prefill 瓶颈是 **专家权重供应与有限 RAM/VRAM 之间的竞争**；长窗口还增加注意力计算及 KV 空间。现有证据不能把整个等待区间解释为 PCIe 饱和，也不能归结为“CPU 没有 AVX-512”。

## 2. 硬件、软件与比较口径

| 项目 | 当前状态 / 解释 |
|---|---|
| CPU | Intel i7-13850HX，8P+12E；检测全部 28 个进程可见逻辑 CPU，支持 AVX2、AVX-VNNI，不支持 AVX-512 |
| RAM | 32GB DDR4，系统可用总量约 31.6GiB；长窗口时物理内存接近用满 |
| GPU | RTX 2080 Ti，22GB 改装显存（22528MiB），Turing / sm75，无原生 BF16 Tensor Core |
| PCIe | 用户重新插拔后从 3.0×4 恢复 3.0×16；启动 H2D 探测约 3.3 → 13.3GB/s |
| GPU 运行条件 | 用户发现降压超频配置异常，并在同电压下降低核心 50MHz，其余不变；没有记录完整电压/显存偏移，不补造数值 |
| 系统 / 引擎 | Windows、Strata 0.1.24 fork；日常端口 8080，单并发 |
| 模型 | Qwen3.8-Flash-Next-GSQ-RCO IQ3_XXS 原生包；专家包历史约 42.8GiB；模型与 PLE 分片均需保留 |
| 构建 | Release、MSVC 19.44、便携 CUDA 12.4、CUDA arch 75、动态 CUDA runtime |
| ggml 依赖 | `3cf03257f219afbe7334045ff7c6a06ac68c627d`；本机外部 llama.cpp-oracle checkout 与仓库 VERSION 固定值一致 |

正式性能测试按单请求串行执行。CPU 多线程、异步 I/O、GPU stream、组件并发读取测试不等于多个用户请求并发；早期吞吐/调试记录的口径以各自报告为准。当前选型针对单并发使用。

比较规则：

1. Decode tok/s、Prefill 引擎耗时、客户端 TTFT、进程启动时间分开。Decode 聚合用总生成 token / 总 Decode 时间；不将逐请求速率均值冒充同一个指标。
2. 进程首次完整长输入、重复完整 Prefill、KV 命中续接分开。“重复完整输入”在正式 Prefill 测试中仍要求 `cache_n=0`。
3. 未清空 Windows 文件缓存，因此进程首次输入/启动不能称为严格冷 SSD 测试。
4. ×4 阶段、GPU 设置异常阶段、×16 稳定阶段不能直接做累积收益推算。报告中的热态漂移、慢样本及失败扫描均保留原说明。
5. 诊断会引入计时开销；主机 staging 与 GPU 重叠，子项不可直接相加。微基准快不等于端到端快。
6. 有限代码题、needle 和数值对拍通过不等于全面模型质量证明。更改驻留/草稿路径的组合不是全模型逐位一致。

## 3. 当前实际配置

完整可移植示例：[current-config.example.json](../../bench/results/2026-10-03-local-optimization/current-config.example.json)。它含路径占位符，使用前必须替换。实际配置快照与小型画像/词表也已归档。

```text
--tiered-experts --expert-cache auto
--host-budget-gib 10 --host-reserve-gib 8
--native-tasks 12 --pcie-frac 0 --skip-empty-pcie
--spec 4 --spec-min-p 0.8 --adapt-every 0
--decode-tuning 31 --commit-async 1
--prefill 16384 --max-context 32768
--turing-prompt-attn 1 --tiered-direct-load 1 --prefill-io-tuning 2
--prompt-cache-root 512 --short-read 448 --refill-mode 3
--prefill-ring 192 --prefill-ring-large 384
--cache-idle-seconds 180 --cache-expire-seconds 3600
--turing-bf16-gemm 0 --prefill-topk-wide 1 --prefill-score-tile 8
```

KV 为默认 FP16，AVX-VNNI 实验开关关闭，预取默认 4 线程，PLE 队列深度 64，CPU 默认队列顺序及单 token 内核不变。MTP 窗口上限为 4；状态中的 `spec=6` 是含 suffix 的内部容量，不能解读成日常已改为 `--spec 6`。大型 ring 在布局 ≥12288 时使用 384，其余通常 192；很小布局仍沿用原 8 槽路径。

## 4. 环境落地与早期纠错

| 方向 / 尝试 | 结果与当前判断 |
|---|---|
| 上游 #87、#80、#130、#134 | 已组装 Turing 支持、三级专家源、安装检测和内存规划；本机补齐 Windows tiered 实现 |
| Windows 文件映射、独立 pinned arena、预取及对齐读取 | 已实现；之后继续修复冗余映射驻留、冷预取与 DMA 能力判断 |
| 0.1.22 对照树、原生路径开关与 NaN 定位 | 做过构建/隔离；旧版 attention 的 sm80 指令需要守卫，不能直接复制到 sm75；并未证明主线 Prefill attention 是 NaN 根因 |
| Q2_0 “全零/坏内核” | 已撤回。旧探针遗漏 `ggml_cpu_init()`，FP16 查找表未初始化；复现 dot 从 0 变为 12803.1875。真实块独立复核正常 |
| IQ1_M “raw 不支持/必然 SEGV” | 已撤回；canonical 与 generic 真实块对照正常，不能继续据此强制升位 |
| 最早 token 0 / NaN 输出 | 当时记录的 38–53 tok/s 不算有效模型性能；打包逐专家尺寸、包格式/升位和 GPU case 的同批修复后恢复，不能把最早故障全部唯一归因于探针 |
| requant 与原生包 | 增加 Q4_0/Q8_0 MMQ 支持，随后原生 IQ3_XXS 作为日常；减少不必要升位造成的容量开销 |
| 原生 IQ2_XS 速度档 | 已验证，专家包约 33.02GiB；早期六题 18.8 vs IQ3 11.6 tok/s。模型量化不同且是旧条件，不与当前 IQ3 67 tok/s 横比；目前未选 IQ2 为日常 |
| 原画像 v1/v2 | 加入 trace-first 与真实路由重排。早期命中率 58.4% → 平均 75.6%；v2 扩充语料后短题速度相近。现已被 Decode+10 的混合画像接替 |
| CPU 功耗条件 50→200W | 历史 IQ3 bench 11.6→17.4、Prefill 415→634.8 tok/s。说明频率/调度敏感，不证明整个引擎只有 AVX 算术瓶颈；本次发布未修改硬件设置 |
| 早期 MTP 扫描 | min-p .3/.4/.5/.6、spec 4/6；当时 .4 更好，6+.3 明显慢。×16 重测后改为 .8；高接受率本身不是优化目标 |
| 旧 Q2 down 分支补丁 | 数值测试通过但整机零收益；该 native_down_rows 分支不在实际 pool miss 调用链，已撤销，不能用来否定真实 VNNI 路径 |
| P 核限定 | 修复线程池尊重进程亲和掩码后，P-only 约慢 7%；亲和修复保留，全 P+E 配置保留 |
| 早期 8K→16K chunk | 核心 90.6→74.7 秒，减少重复专家流入；当时 32K chunk 的 PLE/总耗时更差，保留 16K |
| 增加 stager 到 32 / Prefill 改 pcie-frac .55 | 没有形成收益；Decode 的 pcie-frac 不控制 Prefill 专家传输 |

旧 [FORK_NOTES](../../FORK_NOTES.md) 的第 1–19 节保留现场推断；其中“AVX2 唯一瓶颈”“已无 CPU 软件空间”“IQ1_M 不支持”“不安装任何草稿子词表”等旧断言以本文及后续报告更正为准。

## 5. CPU、内存、PCIe 与 Decode：试过什么

| 方向 | 观察 / 决定 |
|---|---|
| 实际 Q2_0 调用链审计 | 原路径为 AVX2 `vpmaddubsw + vpmaddwd`，并未使用 AVX-VNNI；已有多 token 摊销 |
| AVX-VNNI 专用翻译单元 + CPUID 分派 | 已实现、保留 opt-in；NT4 单核 P 1.127× / E 1.253×，92,160 输出精确一致；×16 整机 58.573 vs 58.571 tok/s，日常关闭 |
| pinned 预算 13/10/8/6/0GiB 等早期筛选 | 13→10GiB 配合内存修复采用；更小预算不普遍更快。不能把首轮驻留进程与重启候选的差异写成稳定 2× |
| 冷预取去重与驻留图检查 | 已采用，避免重复预取和本已驻留的专家触页 |
| Windows 冗余映射页裁剪 | 已采用 VirtualUnlock 等处理，减少专家已有 VRAM/pinned 副本时的额外映射驻留 |
| 动态专家交换 | 关闭；每 4 轮/96 次换入约 40.25 tok/s，每 16 轮/16 次换入长测均值约 55.84，未胜静态 |
| ×4 阶段固定驻留 | 历史不同题集取得 49.38/46.35 tok/s；与后来的 ×16 正式对照分开，不计算累计倍数 |
| PCIe 接触恢复 | 用户硬件修复；×4→×16，启动探测带宽恢复。此前链路问题不是软件 AVX 优化的结果 |
| Windows DMA 能力检测 | 已修复代码；修复后仍由配置显式设 pcie-frac=0，以避免自动分配使本机退化 |
| Decode DMA / direct / kernel 分工 | 扫描 6.25%、12.5%、25%、50%、75%、100% 等；小比例初筛收益未在确认轮重现，保留 0 |
| 空 PCIe CUDA Graph 分支 | ×4 初试慢且未采用；×16 稳定后复测采用。每窗口少 336 节点，单项新旧题约 +1.45%/+2.00% |
| CPU tasks 1/3/6/12/16 | 采用 12；其它 tasks、单 token IQ2_XXS/IQ2_XS/IQ3_S 核、队列排序未胜最终组合 |
| CPU 状态 padding / 分片形状 | 实现并测过，未采用为日常 |
| MTP min-p 0/.2/.6/.7/.8/.9、窗口 6/8 | ×16 最终选 .8、窗口 4；更大窗口增加验证开销 |
| 预取 4/12/16/关闭 | 保留默认 4；关闭的热态约 +0.6% 不抵首次变慢，更多线程略慢 |
| Decode GPU 内核组合 | 采用 tuning=31：HC 单 token 路径、较小分块、分流归一化、激活+量化融合、IQ3_S 跨 token 权重解码复用 |
| 完全融合专家 / persistent blocks / 多种 tile | 已筛选，未形成可部署收益；HC single/tile/both/fuse、gpu15/gpu31 等变体见筛选索引 |
| 专家静态画像：cost/mix/conservative/baseA | 采用独立 16 训练请求与原画像混合的版本；独立 8 题未参与画像训练 |
| 草稿词表：小集/广集、不同阈值 | 采用 88,252 项，包括前 32768 ID、所有 CJK、特殊符号及训练输出 token；目标完整词表不变，不承诺全模型 bit-exact |

正式 Decode 里程碑：

| 对照 | 基准 | 采用结果 | 证据 |
|---|---:|---:|---|
| ×16 tasks12 + min-p .8 + 空图 | 54.682 | 59.360 tok/s（+8.55%） | 新 6 题、4 正式轮；95% 题目聚类区间 +6.41%～+11.97% |
| Decode+10：原 6 题 | 58.853 | 66.123（+12.35%） | 保存原 exe 与原配置对照 |
| Decode+10：独立 8 题 | 61.265 | 67.677（+10.47%） | 未参与画像/词表训练与选参 |
| Decode+10：合计 14 题 | 60.407 | 67.131（+11.13%） | 84 正式请求，3 轮；95% 区间 +8.62%～+14.27% |

单位均为不含 Prefill 的 tok/s。Decode+10 正式三轮收益为 11.48%、10.29%、11.64%；42 对正式文本中 30 对逐字一致，因此不将整个组合声称为数学等价。完整变体列表见 [SCREENING-INDEX](../../bench/results/2026-10-03-local-optimization/SCREENING-INDEX.md)。

## 6. 社区实测经验：采用、放弃与仅调研

检索索引覆盖 502 条 issue/PR，其中深入阅读 32 条；不是完整审计了 502 条，也不是每条均已在本机实测。

| 来源 / 方法 | 本机结果 / 处置 |
|---|---|
| [#207](https://github.com/Niko1221/Strata/pull/207) CPU prefetch | 约 +0.10%，未采用 |
| [#500](https://github.com/Niko1221/Strata/pull/500) 并行中间量化 | 约 +0.20%，未采用 |
| [#284](https://github.com/Niko1221/Strata/pull/284) 异步 commit | 66.164→66.769 tok/s（+0.91%），已采用 |
| [#279](https://github.com/Niko1221/Strata/pull/279) 更大显存余量 | 700→1500MiB 使约 65.7→62.9 tok/s，未采用 |
| [#270](https://github.com/Niko1221/Strata/pull/270) Turing prompt attention | 已采用；8K/16K/31K 吞吐 +9.16%/+9.41%/+15.56%，每长度两对正式样本 |
| [#362](https://github.com/Niko1221/Strata/pull/362) 直接文件读取 | 适配启动 GPU/pinned 填充，已采用；没有整套移植其 GGUF 分片/批量合并/Decode staging |
| [#374](https://github.com/Niko1221/Strata/pull/374) 首块 PLE I/O 重叠 | 已采用；31K 41.887→40.026 秒，吞吐 +4.65%，4 轮；8K 基本无收益 |
| [#439](https://github.com/Niko1221/Strata/pull/439) 批量专家 gather | 保留实验实现但关闭；8K/16K/31K +4.48%/+3.61%/−1.24%，与 PLE 合开也未全面改善 |
| PLE 队列 64→256 | 组件可快约 22%～44%，整机 31K 首次/重复吞吐约 −10.23%/−6.03%，保留 64 |
| 物理核绑定 / 老 Turing GR / sm80 cp.async | 绑定已有；旧 GR 方案有适用/安全限制；sm80 指令不适用本卡，没有盲搬 |
| NVFP4、多 GPU、专家剪枝、混合量化、hugepages | 调研或历史提议，没有纳入当前本机已测收益；未改 hugepages |
| llama.cpp / ik_llama / BitNet 思路 | 作为实现参考，未据其别人的数字宣称本机收益；Q8_0 KV 尚未集成 |

启动直接读取 ABBA：原映射就绪 **80.124 / 69.775 秒**，直接读取 **28.816 / 26.261 秒**；专家填充约 **42–52 → 21–22 秒**。各组驻留数相同，文件缓存未清空；这是启动改善，不能算作 Decode 或每次 Prefill 提速。

## 7. 缓存复用与空闲策略

### 7.1 短前缀与续接

采用 root checkpoint 阈值 **2048→512**、short-read 阈值 **64→448**。前者让约 1K 的共享提示更容易留下可复用根检查点；后者避免小尾巴走过重的完整 Prefill 路径。

同一个 1004-token 共享前缀分支实验：

| 新增 token | 原 TTFT | 优化 TTFT |
|---:|---:|---:|
| 122 | 10.69s | 1.61s |
| 237 | 11.99s | 3.55s |
| 397 | 11.45s | 5.79s |
| 717 | 11.77s | 8.40s |

六请求总耗时 **59.64→33.03 秒（−44.6%）**；首个请求无改善。这是缓存根+短读组合，717-token 场景并未改用 short-read。固定命中 4008 token 的独立测试，较短尾巴改善约 57.5%/46.0%/17.9%；589–717 区间的窗口路径反而慢，故阈值停在 448。对照与 sham 控制保留在归档，不能将复用收益描述为相同完整输入计算快了 44.6%。

### 7.2 空闲落盘 / 过期

已实现并启用 [Idle cache](../idle-cache.md)：

- 最后一次生成完成（包括取消后的 STOP 排空）后开始计时；正在生成不会落盘/过期，health/status 查询不续期。
- 空闲 180 秒写入 snapshot，确认写入后释放会话/MTP 状态 arena 和 CPU checkpoint；模型权重保留。**3600 秒从最后一次生成结束算起**，不是落盘后再等一小时。
- 32K 本机可释放约 **1016MiB VRAM + 225MiB CPU checkpoint**。短对话也可能约 **1.21GiB** 快照，因为当前保存整块预分配状态/工作区。一次记录保存 2.09 秒、恢复 1.56 秒，实际会波动。
- 下一请求可恢复后继续；恢复耗时额外计入客户端等待，不能只看引擎 prompt_ms。文件缺失/损坏回退完整 Prefill；保存失败保留 RAM 并重试。
- 它是当前引擎共享 cache 的生命周期，**关闭一个客户端对话并不等于立刻释放对应 KV**。不是每个对话独立文件，不是聊天记录持久化。
- 快照是进程内临时缓存，不支持跨重启导入；正常退出删除。进程崩溃/停机时计时器不能运行，下一启动清理已过期遗留文件，因此不保证停机中恰好一小时删除。
- 当前支持单 GPU、CUDA VMM、完整驻留 KV；KV streaming、多 GPU 等组合有限制。内存资源释放不保证 Windows working-set/文件缓存计数马上同幅下降。

## 8. Prefill 各轮优化与负结果

### 8.1 长输入权重补回与 ring

采用 `refill-mode=3`：独立 overlapped 句柄的缓存文件读取、4 workers、每线程双 pinned 缓冲；DMA 完成前不复用缓冲，全部补回完成后才发布驻留表。Prefill 的临时工作区会借用专家显存，结束后需要恢复原专家。

同轮保存旧 exe 的 ABBA（无 KV 命中）：

| 输入 | 原耗时 | refill-mode3 + ring192 | 耗时减少 |
|---|---:|---:|---:|
| 8390 token | 14.87s | 13.86s | 6.8% |
| 15956 token | 21.94s | 17.69s | 19.4% |
| 31243 token，进程首次 | 70.26s | 43.92s | 37.5% |
| 31243 token，重复完整读入 | 42.28s | 36.08s | 14.7% |

下一轮采用按布局启用 `ring-large=384`，工作区约 **7.21→7.63GiB**：

| 输入 | 同轮旧版 | 新版 | 判断 |
|---|---:|---:|---|
| 16K | 18.62s | 16.81s | 已确认该轮改善 |
| 31K 首次 | 43.97s | 39.28s | 已确认该轮改善，首次仍波动 |
| 31K 重复完整读入 | 37.14s | 35.73s | 小幅改善 |
| 8K | 15.55s | 13.84s | 路径未改变，不归因于大 ring |

其它已试方向：

| 候选 | 结果 / 处置 |
|---|---|
| 非缓存 direct refill | 热态慢，未采用 |
| 并行映射 refill | 小工作集有收益，但大工作集长尾，未采用 |
| 主体异步 direct read | 未确认稳定收益，最终代码移除 |
| 32K chunk | 核心计算改善，但约 13GiB 专家补回需 5–6 秒、减少中途检查点，保留 16K |
| 固定 ring256 / ring384 | 不普遍优于按布局启用，保留 192 + large384 |
| 对齐直接读入 pinned buffer | 16K 耗时约 35–37 秒，更慢，移除 |
| 文件时间戳导致漏重编译 | 曾发现，修正后重新筛选；被污染轮次已排除，不能作为正式证据 |

### 8.2 最近一轮：Top-K、scorer 与 HC

实现了三项候选：Top-K 按实际活动块数而非预留容量选分支，并扩展 33/65-key 寄存器路径；scorer 在足够长输入下每个 key 复用给 8 个 query；HC 在 sm75 上对可精确转为 FP16 的 BF16 输入尝试 Tensor Core 加速并带回退。

**最终采用 Top-K + scorer；HC 关闭。** 前两项有分数/索引精确对照；HC 即便输入转换精确，累加顺序仍会改变，其微基准改善没充分转化为稳定整机收益。

下表为**三项全开候选**，不是最终配置：

| 场景 | 旧版 | 三项全开 | 样本 / 解释 |
|---|---:|---:|---|
| 32K 容量，31K 首次 | 44.706s | 49.791s | 每组 2；回退且有慢尾 |
| 32K 容量，31K 重复完整输入 | 35.184s | 35.653s | 每组 2；无改善 |
| 32K 容量，8K | 15.679s | 15.195s | 每组 4；约 3% 小幅变化 |
| 256K 容量，128K | 219.749s | 204.446s | 每组 2；耗时 −7.0% |
| 256K 容量，261K | 505.483s | 427.638s | 仅 1 对；耗时 −15.4% |

关闭 HC 后，最终配置单次无诊断 130,048-token 输入 **210.508 秒**，五处检索 **5/5**；缓存续接 **33.1 tok/s**。与旧版两次中位数比耗时 −4.2%，不是新的 ABBA。最终 HC-off 没有重测完整 261K，不承诺它获得表中 −15.4%。

曾观察到三项全开 128K 首次续接只有 15/18.5 tok/s；专项重复同一请求后 HC-off/on 中位数约 **49.9/48.0 tok/s**，没有持续复现两倍回退。首次/重复结果均保留，根因没有唯一确定；不把热态重复值充当首次长上下文的速度。

## 9. 256K 与 KV 量化

模型原生上下文为 262144。把配置容量开到 256K 即使实际输入短，也会影响 KV/工作区规划及专家驻留。日常目前仍 32768，INT8 仍是候选。

| 主 K/V 存储（256K） | 空间 | 当前验证情况 |
|---|---:|---|
| FP16 | 6.00GiB | 已测、日常格式 |
| Strata INT8（group64 + FP16 scale） | 3.09GiB | 已做本机容量/性能/恢复探索，未转为日常 |
| llama.cpp Q8_0（group32） | 理论 3.19GiB | 尚未集成和本机实测，不能与 Strata INT8 混称 |
| Q4 类格式 | 理论约 1.69GiB | 本轮未做相同模型端到端选型验证 |

这些是主 K/V 估计，不包括所有 session/MTP/index/checkpoint/工作区。256K 主实验中，专家显存容量从 32K 的约 **14.54GiB** 降到 **8.44GiB**，Prefill 又临时借约 **7.63GiB**；量化除 KV 带宽外，还可能缓解专家挤出。

此前 256K 容量下的探索性 FP16 / Strata INT8 单样本：

| 实际输入 | FP16 Prefill | INT8 Prefill |
|---|---:|---:|
| 31K | 51.05s | 50.01s |
| 64K | 98.08s | 88.15s |
| 128K | 197.76s | 186.87s |
| 261K | 506.36s | 463.47s |

同轮快照约 **7.75 / 4.60GiB**，恢复约 **9.48 / 5.38 秒**。这是旧轮、不同配置的一次观察，不能与最新 128K 210.508 秒直接推导优化退化；也不足以证明量化质量无损。尚需同配置多轮验证长距离检索、代码/推理、多轮分支及长期恢复后再决定。

## 10. 瓶颈在哪里，还能做什么

Prefill 主要链路：路由确定需要的专家 → SSD/文件缓存读取 → 主机 staging → H2D → GPU 专家计算；同时还有 PLE、HC、QSA 打分/Top-K/attention，以及结束时的专家补回。跨 chunk 重复供应和显存借用使“模型容量”成为实际性能问题。

最近诊断中 wait-copy 区间约占 31K 的 **26%**、128K 的 **40%**。它包含供应未就绪、调度、传输等影响；没有足够证据拆成纯 SSD、纯 CPU copy 或纯 PCIe 饱和。本机 NVML RX 采样与实际工作不相称，没有用它认定链路达到上限。CPU pool GB/s 同样只是压缩权重字节/整个阶段耗时，不是硬件 DRAM 实测带宽。

| 优先级 | 方向 | 现状 / 预期边界 |
|---|---|---|
| 高：软件定位 | 分离冷读、staging、H2D；统计每 chunk 冷专家字节与复用 | 尚未完成充分归因，应先得到可信瓶颈分布 |
| 高：减少数据移动 | 跨 chunk 专家复用、降低 Prefill 工作区、减少借出/补回 | 有结构性空间，但已有 ring/异步/双缓冲，继续加线程不一定快 |
| 高：RAM 容量 | 验证 64GB 或更大 RAM、重新规划 pinned 与系统余量 | 可能减少磁盘读和长尾，未在新硬件测试，不给百分比保证 |
| 中：KV | 独立选择 INT8 或集成 Q8_0，验证质量与全链路 | 主要针对长窗口容量/恢复，32K 不必先量化 |
| 中：GPU/VRAM | 更大显存减少专家与 KV 竞争，新架构改善 BF16/attention | 合理硬件方向，未实测升级收益 |
| 较低：现有 CPU 微调 | 更深入 IQ gate/up 微架构优化、实际热点变化后再测 VNNI | 已试的大量调度/分片/阈值旋钮收益收敛；AVX-512 标签不能替代整机验证 |

因此，**Prefill 没有被证明“已无优化空间”**。目前是易验证的小参数收益逐渐收敛，剩下更值得做的是降低权重流量与容量压力。旧计划中的“再提高 20%～30%”“混合量化约 +12%”“画像每轮 +3%～5%”都是预测，尚未验证，不能记入已实现成果。

## 11. 正确性、稳定性与本次发布核对

| 项目 | 已完成验证 / 限制 |
|---|---|
| GPU 稳定性复查 | 用户调整配置后，原 CUDA Graph/eager 130,000 次对照通过；不证明永久稳定，不据此判定显卡物理损坏 |
| 历史 CPU 0xc0000005 | 曾落在只操作寄存器的 AVX 指令、异常地址差一个 bit；根因未确认。后续 400 次 CPU 对拍与 1902 个完整模型请求未复现，但不能宣布已修复 |
| CPU / GPU Decode | CPU 池 88,473,600 项精确与 sentinel 比较；IQ3_S GPU 1,953,792 项逐位有限值比较；有限代码/召回检查通过 |
| Prefill refill / I/O | 45 项 staged-refill 测试、512 次并发 Windows cached/stream 读取；真实模型全部 4465 个补回槽位与源权重逐字节一致 |
| 最新计算候选 | BF16 13 例、Top-K 12 例、scorer 7 例；三个 Compute Sanitizer memcheck 均 0 错误；CLI 27 例 |
| 缓存集成 | 完整 31K、驻留重试、落盘恢复、续接/分支、Prefill 取消后恢复、过期后重读；生产配置回归通过 |
| 本次发布重新执行 | `python -m unittest serve.test_server -q`：**40/40 通过**，10.286 秒，mock engine；不与其它轮次 39/42 项的不同组合混为同一套 |
| 源码与二进制 | frozen 记录的 **236 个文件 SHA-256 全部匹配**；当前 exe 与已验证候选哈希相同；本次只新增总结、归档与复现资料，没有重跑 GPU 性能实验 |
| 未完成项 | 未重新执行全库 CTest；历史扩展 CTest 28/29 中 PLE 对照缺原始 fixture，不能记作全绿；未做全面语言模型质量评测 |

当前已验证 exe SHA-256：

```text
4feb4d78fff931c239515d2ce0c05cd6c7be366a7bf29949dfb21b7c2636684a
```

发布仓库为 [W1nge/Strata](https://github.com/W1nge/Strata)，分支 [codex/avx-vnni-q2](https://github.com/W1nge/Strata/tree/codex/avx-vnni-q2)。该分支保留原有历史及现有全部相关源码改动，并随提交加入本总结与小型证据；不覆盖 main/turing-tiered-win。精确发布提交由包含本文的 Git commit 标识，避免文档自引用哈希。历史报告中的“未提交/未推送”仅描述当时状态。

## 12. 资料与复现入口

- [结果包 README](../../bench/results/2026-10-03-local-optimization/README.md)：配置、构建要求、资产使用方法、资料边界。
- [55 份筛选摘要索引](../../bench/results/2026-10-03-local-optimization/SCREENING-INDEX.md)：保留 variants、请求数、速率及不同数据结构入口。
- [发布核对记录](../../bench/results/2026-10-03-local-optimization/publication-validation.json)、[来源/发布 SHA-256 清单](../../bench/results/2026-10-03-local-optimization/manifest.json)。
- 本机保留更大的原始输入、日志、历史二进制、源快照和证据 ZIP；Git 不包含模型权重、exe/DLL、KV 快照或内存转储。归档 JSON 中个别路径/附件名因此指向本机材料，不能当作仓库内可点击文件。

16 份阶段报告均附历史状态说明，按演进顺序阅读：

| 阶段 | 报告 |
|---|---|
| CPU 调用链、探针、指令集 | [CPU-AVX-REVIEW](archive/CPU-AVX-REVIEW.md) |
| VNNI 实现与预算初筛 | [IMPLEMENTATION-RESULTS](archive/IMPLEMENTATION-RESULTS.md) |
| ×4 内存修复与 Decode | [DECODE-40-RESULTS](archive/DECODE-40-RESULTS.md) |
| 联合 profiling、空图初试 | [PROFILE-AND-NEXT-STEP](archive/PROFILE-AND-NEXT-STEP.md) |
| 当阶段剩余瓶颈 | [REMAINING-BOTTLENECKS](archive/REMAINING-BOTTLENECKS.md) |
| ×16 与 GPU 设置稳定性 | [GPU-STABILITY-X16](archive/GPU-STABILITY-X16.md) |
| ×16 参数收敛 | [CONTINUOUS-OPTIMIZATION-X16](archive/CONTINUOUS-OPTIMIZATION-X16.md) |
| Decode 再提高 10% | [DECODE-10-RESULTS](archive/DECODE-10-RESULTS.md) |
| 社区第一轮 | [COMMUNITY-EXPERIMENTS](archive/COMMUNITY-EXPERIMENTS.md) |
| 社区第二轮、启动与 PLE | [COMMUNITY-EXPERIMENTS-2](archive/COMMUNITY-EXPERIMENTS-2.md) |
| 短前缀和短尾巴 | [PREFILL-CACHE-OPTIMIZATION](archive/PREFILL-CACHE-OPTIMIZATION.md) |
| 长 Prefill 与 refill | [PREFILL-LONG-OPTIMIZATION](archive/PREFILL-LONG-OPTIMIZATION.md) |
| 空闲缓存策略 | [CACHE-IDLE-POLICY](archive/CACHE-IDLE-POLICY.md) |
| 按布局大 ring 与加载 | [PREFILL-LOADING-OPTIMIZATION](archive/PREFILL-LOADING-OPTIMIZATION.md) |
| 256K 与 INT8 候选 | [CONTEXT256-COMPARISON](archive/CONTEXT256-COMPARISON.md) |
| 最新三候选及最终采用 | [prefill5-report](archive/prefill5-report.md) |
