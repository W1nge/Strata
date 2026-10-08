# Part2: MTP for longer code generation — 2026-10-08

后续引擎与代码编辑更新见 [PART2-MAPPED-OUTPUT-2026-10-08.md](PART2-MAPPED-OUTPUT-2026-10-08.md)。下文保留本阶段的原始测量与配置，当前 coding 配置已在后续阶段更新。

追测此前的 115.3 token/s 后，为短提示、长代码输出采用独立配置：**原专家画像 + `--spec 8 --spec-min-p 0.9`**。四类代码任务各重复两轮，输出加权吞吐从 **83.79 提高到 89.21 token/s（+6.47%）**，两个候选轮次分别为 89.12、89.30。这里没有建立长输出持续 115 token/s 的结论。

代码配置已保存到 `C:/strata-models/strata-dual-p100-coding.json`，启动文件为 `C:/strata-models/run-iq3xxs-dual-p100-coding.bat`。它使用已有的稳定引擎 `E:/strata-setup/part2-helper-resident/strata.exe`，引擎源代码提交为 `4cda6e0`。本轮不增加生产引擎代码；MTP 置信度截断是已有功能。

通用双卡配置仍是 `strata-dual-p100-experimental.json` 的 spec4 / 0.8；原单卡 256K 配置继续保留。新配置的上下文上限为 **8192**，本轮测量的长代码任务只有 **256–303 个输入 token**，不能据此推断长上下文代码编辑、其他语言或开启 thinking 后的收益。

机器为 i7-13850HX / 32 GB RAM、2080 Ti 22 GiB / 310 W、P100 16 GiB / 250 W，Windows WDDM、无 P2P，驱动保持 537.13。2080 Ti 负责主干、KV、输出头和 MTP，P100 负责辅助专家，CPU 负责剩余专家。模型为 Qwen3.8-Flash-Next IQ3_XXS，INT8 KV；沿用 resident helper、`--short-read 448`、固定专家布局和 6 GiB RAM 余量。

共完成 **7 次串行模型启动、55 个响应**，其中 **45 个较长代码响应、10 个短探针**。所有响应通过功能检查，且 `finish_reason=stop`。这些是有限的任务检查，不是完整的代码质量评估。短探针不参与下表和持续吞吐统计。

| 工作负载 | 每次输出 token，原 → 新 | spec4 / 0.8，token/s | spec8 / 0.9，token/s | 吞吐提升 | 平均完整请求秒数，原 → 新 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 个列表与数学工具函数 | 781 → 721 | 81.23 | 90.83 | +11.81% | 12.39 → 10.22 |
| TTL + LRU 缓存类 | 500 → 511 | 83.72 | 89.68 | +7.11% | 8.58 → 7.83 |
| 拓扑排序、最短路径、LCS | 946 → 962 | 83.32 | 88.46 | +6.17% | 13.61 → 12.78 |
| 12 个矩阵函数，含乘法与快速幂 | 1456 → 1302 | 85.56 | 88.70 | +3.67% | 19.72 → 16.95 |
| 合计，两轮各四项 | 7366 → 6992 | 83.79 | 89.21 | +6.47% | 总计 108.61 → 95.56 |

吞吐按 `sum(predicted_n) * 1000 / sum(predicted_ms)` 计算，完整请求耗时另计，包含 prompt 处理及 HTTP 开销，排除模型加载和离线功能检查。完整请求总耗时减少 **12.02%**，其中也包含输出长度变化，不能全部归因于生成吞吐。IQ 模型的多 token CPU 运算及 CPU/GPU 专家运算舍入不同，改变验证窗口或专家分布可能生成不同的有效代码；这里不宣称逐 token 一致。

复测是在各自的一个进程内各执行两轮，候选先跑、基线后跑，未随机交错；样本量不足以给出统计置信区间。两轮所有长代码请求的 `cache_n=0`。首次遇到某些窗口时仍包含 CUDA graph 捕获开销，并非所有窗口均已预热。矩阵模块在筛选窗口和门槛后才加入，未用于选择 0.9 门槛。

三项初筛代码任务的加权吞吐为：spec4 / 0.8 **81.03**，spec6 / 0.8 **87.49**，spec8 / 0.8 **88.36 token/s**。随后在同一 spec8 进程按 0.8、0、0.5、0.9 顺序扫描置信度门槛：

| 草稿置信度门槛 | 输出加权 token/s |
| --- | ---: |
| 0.8 | 86.66 |
| 0，强制延长窗口 | 72.59 |
| 0.5 | 81.23 |
| 0.9 | 89.82 |

`--spec 8` 是验证窗口上限，`--spec-min-p 0.9` 在草稿置信度不足时提前缩短窗口；每个草稿仍由主模型检查。强行填满窗口的成本抵消了批量验证收益，因此采用 8 / 0.9，随后使用上述独立启动的两轮验证确认它的表现。

还测试了上一轮独立训练的专家画像与 8 / 0.9 的组合。画像由 3 个独立英/中文及合并有序列表请求采集，493,920 个专家路由、覆盖 48 层，`make_profile.py --reorder` 生成完整 24,576 对排序，未用本轮验证任务训练。

组合画像的两轮整体吞吐为 **89.73 token/s**，只比原画像的 89.21 高约 0.6%；完整请求合计 **97.92 秒**，比原画像的 95.56 秒更长。工具函数和矩阵更快，TTL 与算法模块更慢；两轮整体为 87.26 / 92.35，波动也更大。因此仍采用原画像，不增加另一个日常配置。新画像提升主卡专家命中率，但命中率本身不能代替完整请求的计时。

短代码的速度上限可以再次看到：组合画像第二轮探针输出 **53 token / 462.0 ms = 114.7 token/s**，45/45 草稿接受，完整请求 0.789 秒。此前的 **115.3** 同样只有 53 token，生成耗时 459.5 ms。它们说明短而容易预测的代码确实能达到这个速度，不能代表数百至上千 token 的持续吞吐。

每个请求的引擎日志都报告 **0 次专家文件源 blob 读取**；CPU 专家副本约 10.83–10.84 GiB，经 VirtualLock 驻留。该计数不包括启动时载入权重或 PLE 等其他文件访问，也不等于所有物理 SSD I/O 都为零。

`tools/bench_mtp_coding.py` 检查空输入、边界值、LRU 淘汰与 TTL 到期、平行边、环、不可达节点、子序列、矩阵行独立性与部分输入不变性等。生成代码经过 AST 限制，在带受限 builtins 的独立 `python -I` 子进程执行，限时 5 秒。这是用于本地基准的受限执行方式，不是安全沙箱。

新配置的 `.shared-settings.json` 将缺省请求设为 `temperature=0`、`reasoning_effort=none`，与本轮请求一致；客户端明确提供的参数仍优先。启动文件打开本机 `http://127.0.0.1:8080`。参数、原画像和稳定引擎与通过验证的 `mtp8-p90-b` 相同，仅将运行日志改为 `coding-engine.log`；不需要换驱动或模型文件。默认请求和基准请求的模板输入已作离线等价检查。测试进程均已结束。

原始证据位于 `E:/strata-setup/part2-mtp-coding`，仓库归档为 `bench/results/2026-10-08-part2-mtp-coding`，含实际配置、完整响应、引擎与服务器日志、计划、汇总和安装副本。`receipt.json` 记录源文件及安装文件的 SHA256；可执行程序和大模型文件没有重复提交。仓库范围仅为基准工具与证据，不把这些本机参数加入上游默认值，也不新增重复的引擎 PR。

在仓库根目录复现，使用相同模型文件、兼容驱动的引擎、空闲端口和新 label，串行执行：

```powershell
python tools/bench_part2_tuning.py coding-base-new --config bench/results/2026-10-08-part2-mtp-coding/general-config.json --out E:/strata-setup/part2-code-recheck --coding --coding-long --rounds 2
python tools/bench_part2_tuning.py coding-mtp8-new --config bench/results/2026-10-08-part2-mtp-coding/general-config.json --out E:/strata-setup/part2-code-recheck --coding --coding-long --rounds 2 --overrides '{"spec":8,"spec_min_p":0.9}'
python bench/results/2026-10-08-part2-mtp-coding/summarize.py
```

前两个命令重新测量；最后一个命令仅从归档重算本文结果。归档配置保留本机绝对路径，在其他机器上复现需要修改路径并重新测量。
