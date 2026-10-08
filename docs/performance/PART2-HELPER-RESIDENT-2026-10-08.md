# Part2：固定辅助卡的剩余专家驻留 RAM（2026-10-08）

## 实现与采用

用户要求发挥两张卡和系统 RAM 的能力，并保持 2080 Ti 承担主干、P100 和 CPU 分担剩余专家。已接入上游现有 cache-complement planner：从 RAM 副本中排除主卡和所有辅助卡已持有的专家。引擎改动 14 行新增、2 行删除；原有容量检查、分配/锁页回退和文件源保持可用。新增正向测试覆盖主卡/辅助卡/CPU 三份可变 blob 布局与文件回退。

此方向与社区 [PR #1184](https://github.com/Niko1221/Strata/pull/1184) 重叠；最终审查时核对了该 PR，明确注明来源，不再另发重复功能 PR。本地版本范围更严格：辅助卡与 resident 模式同时启用时，若 adapt_every 和 adapt_swaps 均启用则启动拒绝。它不实现辅助卡动态换入换出后的 RAM 所有权维护。当前配置两者都为 0。

源代码提交 4cda6e0（codex/helper-resident-complement，已推送），已同步日常源码。独立程序 E:/strata-setup/part2-helper-resident/strata.exe；双卡实验配置 C:/strata-models/strata-dual-p100-experimental.json 已指向它。模型 IQ3_XXS，驱动 537.13，2080 Ti 310W、P100 250W，INT8 KV、MTP spec4、max-context 8192、prefill auto、short-read 448、pcie-frac 0、resident-experts、RAM headroom 6 GiB。原单卡 256K 配置不变，双卡 idle offload 仍关闭。

本机实际 4K/8K 配置分别将剩余 10.77/10.83 GiB 专家完整锁在 RAM。CUDA host allocation 被驱动拒绝，已有 Windows VirtualLock 回退成功（11027/11091 MiB），因此是锁定的 CPU 内存，而非全部 DMA-mapped 内存。主卡约 14.85 GiB 专家、P100 约 14.29 GiB，与 RAM 副本互补。启动需要额外约 15–18 秒建立 RAM 副本。其他程序占用更多内存时，原有软回退仍可能只驻留部分或退回 mmap，不保证每次都能完整锁定。

## 实测

所有下列 HTTP 运行先验证 2+2 首次及重复请求，再运行 workload；均正常停止，回答检查通过。short workload 重复 apple 30 次；steady workload 对 1..100 的所有输出数字逐项核对，产生 391 个 token。完整输出与时序在同日期证据目录。

| 配置/任务 | 输入 token | 输出 token | 提示处理秒数 | decode token/s |
|---|---:|---:|---:|---:|
| resident-helper | 268 | 31 | 3.039 | 82.6 |
| resident-large | 1228 | 31 | 21.382 | 58.1 |
| mmap-large | 1228 | 31 | 25.183 | 29.8 |
| resident-large-steady | 1232 | 391 | 21.521 | 76.7 |
| mmap-large-steady | 1232 | 391 | 28.971 | 42.2 |

之前相同短 helper/mmap 任务为 9.405 秒、36.4 token/s（Part2-helper 记录）；resident-short 为 3.039 秒、82.6 token/s。短任务走 short-read 路径，不能用来代指批量 prefill。1228/1232-token 任务实际触发批量 prefill，模型启动日志解析到 auto 8192 的 workspace/ring。最初测试参数 auto:2048 在此上游实际会被归一为默认 8192；最终配置使用明确的 auto，不再暗示 2048 上限。

较长输出同一任务的对照为 42.2 -> 76.7 token/s，提示 28.971 -> 21.521 秒。本轮不是多轮随机交错正式 benchmark；温度、OS 文件缓存、先后顺序及不同提示的 MTP 接受率仍限制外推。没有宣称所有场景加倍、满 8K 或 256K 提示已通过质量/性能验证。

## SSD 边界和正确性

resident-short 的运行时专家文件源计数为 0，CPU 所需专家来自 RAM。长提示的统计为 9710 次文件源 blob 读取：prefill 仍可能通过文件源获取已在 GPU 上的专家，或恢复被借走的主卡 cache slots。文件源读取不等于每次都发生物理 SSD 读取（可能命中 OS 缓存）。PLE 及启动加载仍读文件。因此本次消除的是 CPU 专家缺失对应的反复回读风险，并未实现整个程序完全无 SSD。

file_expert_source_test 全部通过（含新增互补布局检查）；完整 engine 重新构建通过；启用动态 helper adaptation 的 CLI 组合在加载模型前返回 2，Python 校验了退出码和诊断。现有 server 代码与 GPU kernel 未改变，未重跑无关服务器全集。未测试 Linux/HIP、多于一张 helper、动态交换或内存压力下的完整模型回退。

## 回退与证据

切回 C:/strata-models/strata-dual-p100-mmap.json 可恢复上一版 helper 配置；更早分层配置在 strata-dual-p100-layer-split.json。新代码在 resident 模式关闭时保留原路径。原始 engine/server/build/test 日志在 E:/strata-setup/part2-dual；bench/results/2026-10-08-helper-resident/receipt.json 记录代码与程序/配置/日志 SHA256，保存 HTTP 结果和复现脚本。没有更改用户在旧审计文档中的未提交编辑。
