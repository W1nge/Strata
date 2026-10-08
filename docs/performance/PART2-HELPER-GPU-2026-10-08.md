# Part2：2080 Ti 主卡 + P100 专家辅助卡（2026-10-08）

用户决定将主干重计算留在 2080 Ti，剩余专家由 P100 和 CPU 分担。已使用上游现有 helper 模式跑通并保存为当前双卡实验配置；没有修改或发布引擎代码。

## 分工与配置

- 2080 Ti（310W）：全部主干层、KV/session、输出头、MTP，以及主卡驻留专家。正常批量 prefill 仍由主卡处理。
- P100（250W）：保存主卡未驻留的一部分专家，在 helper 路径计算其专家行；不接管一段完整模型层。
- CPU：处理两张卡均未驻留的专家。分配基于专家驻留及路由，并非测得吞吐量后的 P100/CPU 自动负载均衡。
- 两卡无 P2P，使用 pinned 主机缓冲传输；`--remote-expert-opt` 将辅助卡的加权部分和在卡上归约后回传，减少回传量。每层仍可能等待辅助卡，不保证所有请求更快。

当前配置 `C:/strata-models/strata-dual-p100-experimental.json` 使用 `--gpu 0,1 --expert-cache-device1 auto --remote-expert-opt --mmap-experts`，没有 layer-split。为避免当前 server 将多个 config.gpu 自动转换为 layer-split，卡列表传给引擎 --gpu，而不设 config.gpu。主卡及辅助卡专家数量按可用显存自动决定；本次主卡 9199 slots / 14.91 GiB。

helper 不兼容原 8 GiB resident-cpu-experts 内存预算。首次启动明确拒绝此组合；移除预算后，默认整份 resident arena 导致无法为主卡专家缓存分配足够资源，也失败。最终显式 --mmap-experts，通过 OS 文件缓存读取专家，完整启动和请求通过。上述失败日志在 E:/strata-setup/part2-dual/helper310*，未覆盖。

## 310W 下的初步配置对照

同一构建、IQ3_XXS、INT8 KV、4096 context、MTP spec4。每次检查 2+2 首次与重复请求，再测试 268-token 输入、31-token 输出的 apple 重复任务。两种配置均通过。

| 配置 | 提示处理 | 解码 |
|---|---:|---:|
| 分层 auto + coverage=3，8 GiB resident budget | 16.811 秒 | 38.5 token/s |
| 2080 Ti 主卡 + P100 helper，mmap | 9.405 秒 | 36.4 token/s |

一次短任务对照，不是严谨的纯分工 A/B：驻留内存策略同时变化、OS 文件缓存和先后顺序可能影响结果。此提示短于 short-read 448 阈值，不能当作长提示批量 prefill 吞吐量；长期生成、长上下文、多轮聊天、取消均未在新 helper 配置专项验证。没有逐位等价或普遍加速的主张。

本次 helper workload 日志记录 CUDA1 50,835 expert entries、3,657 active layer launches、140.1 MiB 返回（未归约完整行估算为 1,401.0 MiB），host staging/launch 184 ms、等待 1,133 ms。这些是整次请求计数，不是单独 decode 时长，不能相加解释所有墙钟时间。

当前实验容量仍为 4K，idle session offload 仍关闭。旧分层配置备份在 C:/strata-models/strata-dual-p100-layer-split.json；单卡 256K 日常配置保持原状。测试进程已正常退出。完整输出及安装 hash 在 bench/results/2026-10-08-part2-helper/；引擎日志在 E:/strata-setup/part2-dual/。
