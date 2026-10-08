# Part2: mapped helper output and code-edit latency — 2026-10-08

本轮为 coding 配置安装了两项改进：辅助显卡直接将归约结果写到已有的映射主机缓冲区，以及把短提示词阈值从 `--short-read 448` 提到 `1024`。同顺序复测中，单独的引擎补丁让四类长代码吞吐从 **89.41 到 90.42 token/s（+1.13%）**；组合配置让两次完整模块编辑的总耗时从 **50.75 到 34.78 秒（减少 31.47%）**。组合的长代码吞吐为 88.89 token/s，与该对照基本持平（−0.58%）。较大的编辑收益来自提示词处理，且包含输出长度变化。

使用原有的 `C:/strata-models/run-iq3xxs-dual-p100-coding.bat` 启动即可。`strata-dual-p100-coding.json` 现在指向 `E:/strata-setup/part2-mapped-output-20261008/strata.exe`，引擎源码提交 `b71819def39f82fa320887a37da0d514efe59fa4`，程序 SHA256 为 `38ad7934bb1e3cbbe29a3bcd1da5d749a648c51de5b4dc628dc52a6212f7d0b8`。保留 spec8 / 0.9、原专家画像、suffix0、CPU 默认线程池、1024 MiB 显存预留、8192 上下文和 INT8 KV。已有 shared settings 仍将缺省请求设为 temperature0、thinking 关闭。

通用 spec4 / 0.8 配置完成兼容性比较后，**保留原引擎和 short-read448**：新引擎的完整请求时间几乎相同，而这组生成吞吐低了约 2%。原单卡 256K 配置也保留。旧可执行文件 `E:/strata-setup/part2-helper-resident/strata.exe` 和两份原配置的逐字节副本仍在；`install-receipt.json` 记录安装、保留和回退文件的哈希。

机器为 i7-13850HX / 32 GB RAM、2080 Ti 22 GiB / 310 W、P100 16 GiB / 250 W，Windows WDDM、无 P2P，驱动 537.13。模型为 Qwen3.8-Flash-Next IQ3_XXS；2080 Ti 承担主干、KV、输出头和 MTP，P100 承担辅助专家，CPU 的剩余专家副本约 10.84 GiB，经 VirtualLock 驻留，保留 6 GiB RAM 余量。原引擎代码为 `4cda6e0`；它到本轮父提交 `54d2453` 之间没有引擎改动。新程序在相同 CMake 构建中用 MSVC、CUDA 12.4.131、`60-real;75-real`、实验性 SM60 支持编译通过。

引擎原先即使已经有 `h_out_` 的设备映射，也会把辅助专家的加权和写到 `p.sum`，再逐层调用 `cudaMemcpyAsync` 复制到 `h_out_`。本轮让已有的 `zero_copy_` 能力检测选择 `z_out_` 为归约输出；`finish()` 仍先同步同一流，再由 CPU 累加结果。映射不可用或 `STRATA_REMOTE_ZEROCOPY=0` 时继续使用原来的设备缓冲区和复制路径。归约算术、缓冲区大小和分配方式没有改动；回传数据仍跨越 PCIe，省下的是显式复制及其提交开销。生产代码差异仅为 `src/core/remote_expert_opt.cu` 的 **+5/−1 行**，没有新增参数或显卡型号判断。

全部完成 **13 次串行模型启动、137 个响应**：66 个较长代码生成、14 个模块编辑、21 个短探针、36 个通用响应。所有响应通过本地检查，且 `finish_reason=stop`。这些是有限的功能与格式检查，不是全面的模型质量评估。以下长代码统计只包含 utilities、ttl_cache、algorithms、matrices 四项；每次进程执行两轮，排除短探针和编辑任务。

| 测试 | 四类长代码的输出加权 token/s | 八个完整请求合计，秒 | 判断 |
| --- | ---: | ---: | --- |
| `baseline-a`，当前原版初始对照 | 87.74 | 97.08 | 初筛基线 |
| `reserve2048-a`，预留 2048 MiB 显存 | 85.24 | 101.86 | 不采用 |
| `cpu-auto-a`，自动 P 核线程池 | 87.99 | 96.69 | 增幅不足以采用 |
| `suffix-a`，suffix draft3 | 89.01 | 94.70 | 收益不均匀，不采用 |
| `mapped-output-a`，只改引擎 | 92.13 | 92.26 | 第一次候选测量 |
| `mapped-control-b`，同顺序原版对照 | 89.41 | 95.19 | 补充对照 |
| `mapped-output-b`，同顺序引擎复测 | 90.42 | 94.18 | +1.13% 吞吐、−1.07% 请求时间 |
| `combined-a`，新引擎 + short-read1024 | 88.89 | 95.96 | 为编辑等待时间采用 |

吞吐按 `sum(predicted_n) * 1000 / sum(predicted_ms)` 计算，完整请求时间另外累加，包含提示词与 HTTP 开销，排除模型加载和离线检查。初筛基线没有在轮次之间插入编辑任务；两个 `mapped-output`、`mapped-control-b`、`combined-a` 的顺序相同：探针、四项长代码、编辑，再重复。测试没有随机交错，GPU 动态时钟、Windows 调度、文件缓存和首次 CUDA graph 捕获都会造成波动，样本不足以给出统计置信区间。首次候选相对初筛为 +5.01%，相对同顺序对照为 +3.05%；复测只有 +1.13%，因此不把最佳一轮作为稳定收益。

两个引擎候选各自的 12 个响应均与 `mapped-control-b` 逐字一致，每轮四项长代码各输出 721 / 511 / 962 / 1302 token。相同的八项长代码共 88,460 次辅助层启动、4,556 MiB 逻辑回传；`mapped-control-b` → `mapped-output-b` 的主机提交时间为 **2673 → 2119 ms（−20.7%）**，等待辅助卡完成为 17137 → 17010 ms。减少提交开销可以复现，整机吞吐增幅较小。它们不证明其他显卡或负载也会提速。

新的编辑用例输入 **878 token**，要求完整保留八个工具函数，再添加使用单调队列的 `window_minimum`。检查保留函数的边界行为，以及新增函数的空输入、重复值、递增、递减、无效窗口和输入不变性。fixture 来自上一轮已通过检查的工具模块；运行的是完整响应，代码检查仍在有限 builtins、AST 限制、5 秒超时的独立 Python 子进程中进行，这不是安全沙箱。

| 同顺序的编辑比较 | 提示词处理，秒 | 输出 token | 生成 token/s | 完整请求，秒 |
| --- | ---: | ---: | ---: | ---: |
| 原版448，第一轮 | 20.070 | 1048 | 87.4 | 32.064 |
| 新引擎1024，第一轮 | 6.867 | 931 | 88.1 | 17.440 |
| 原版448，第二轮 | 5.721 | 1048 | 80.9 | 18.681 |
| 新引擎1024，第二轮 | 6.842 | 931 | 88.7 | 17.338 |

这两次编辑合计减少 31.47% 请求时间；提示词合计 25.79 → 13.71 秒。组合配置生成了另一份通过检查的代码，每次少 117 token，因此不能把全部时间变化算作推理加速。包含短探针、长代码和编辑的完整 12 请求序列为 **148.16 → 133.06 秒（−10.19%）**，输出总量为 9194 → 8960 token。

short-read1024 也有取舍：在另一轮只改引擎、仍用448的复测中，两次编辑为 29.12 / **14.90 秒**，后一次比1024的17.34秒快。更早原版448的两次编辑为49.56 /16.62秒，原引擎1024为18.32 /17.25秒。这里的第一、第二轮指同一进程的执行顺序；这些编辑的 `cache_n` 都为0，并非提示词 KV 缓存命中。选择1024是为了缩短这类新模块编辑的首次等待，接受预热后批量路径可能更快的取舍；只改 coding 配置，不改上游默认值。

原因可从专家来源看见：448的批量提示词路径借用主卡专家缓存，随后重填，CPU 驻留副本未包含的专家还要访问文件源；每个编辑请求增加7531次文件源 blob 读取。日志里的数量是累计值，第二轮为15062；它不是物理 SSD I/O 计数。1024让该模块经验证窗口读取，保留 GPU 专家布局，组合测试所有请求的文件源 blob 读取均为0。该指标不包含启动载入或其他模型文件访问，也不说明任意长提示词都能避开文件源。

通用 spec4 / 0.8 对照和候选各18个响应，覆盖问答、短代码、平方数、英文说明、928 /1924 /5107 token 检索以及缓存复用。两份输出18/18逐字相同，重复缓存请求均重用19个输入 token。完整请求合计 **123.76 → 123.37 秒（−0.32%）**；输出加权生成吞吐 **73.86 → 72.27 token/s（−2.15%）**。该混合任务包含很短输出，不作为长输出吞吐。通用结果没有建立性能收益，故日常通用配置保留旧可执行文件。本轮未测试 AMD/HIP 硬件、其他模型、其他语言或 thinking 开启时的效果。

其余筛选结果：2048 MiB 显存预留扩大了 CPU 专家补集到约11.84 GiB，减少主卡专家槽位，生成下降2.85%，继续用1024 MiB。`--pool-affinity auto` 在本机选择7个 P 核工作线程加主线程；默认19个工作线程加主线程，前者仅提升0.28%，继续用默认。suffix3整体提升1.45%，不同任务和轮次不一致，且改变了部分输出，继续用suffix0。这些本机选择都不加入引擎 PR。

新引擎关闭共享映射的回退路径另跑了探针、工具函数、矩阵模块三项，全部通过，并与原版对应输出逐字一致。安装程序核对可执行文件哈希，以及所用配置与 `combined-a` 除 exe/cwd/log 外完全相同。旧引擎仍在原路径，原 coding 配置保存在 `E:/strata-setup/part2-coding-next/rollback-coding-config.json`；恢复它即可回到旧引擎和448。测试进程及端口18997监听均已结束；驱动、功率上限和原单卡256K配置的状态已核对。

原始记录位于 `E:/strata-setup/part2-coding-next`，仓库归档为 [bench/results/2026-10-08-part2-mapped-output](../../bench/results/2026-10-08-part2-mapped-output)。归档包括实际配置、完整响应、日志、构建记录、原补丁、安装与回退配置以及 SHA256 清单。可执行文件和模型不提交。生产改动单独提交；上游分支 `codex/remote-reduced-mapped-output` 从 `d5ea713` 起，只包含相同的六行差异（提交 `2edbb0535633bd9a78f899286b57b831e2381bf1`），不捎带本地 resident helper 改动、基准文件或本机配置。

在仓库根目录用相同模型、兼容引擎、空闲端口和新 label 串行复现；归档配置保留了本机绝对路径，在其他机器上需要修改路径并重新测量：

```powershell
python tools/bench_part2_tuning.py next-old --config bench/results/2026-10-08-part2-mapped-output/rollback-coding-config.json --out E:/strata-setup/next-recheck --coding --coding-long --coding-edit --rounds 2
python tools/bench_part2_tuning.py next-new --config bench/results/2026-10-08-part2-mapped-output/installed-coding-config.json --out E:/strata-setup/next-recheck --coding --coding-long --coding-edit --rounds 2
python tools/bench_part2_tuning.py next-engine-only --config bench/results/2026-10-08-part2-mapped-output/rollback-coding-config.json --out E:/strata-setup/next-recheck --coding --coding-long --coding-edit --rounds 2 --overrides '{"exe":"E:/strata-setup/part2-mapped-output-20261008/strata.exe"}'
python bench/results/2026-10-08-part2-mapped-output/summarize.py
```

前三条重新测量；最后一条只重算归档结果。前一阶段的 MTP8 /0.9 选择见 [PART2-MTP-CODING-2026-10-08.md](PART2-MTP-CODING-2026-10-08.md)。本轮短探针不进入持续吞吐结论，也没有建立长输出持续115 token/s的结果。
