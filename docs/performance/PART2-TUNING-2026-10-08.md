# Part2 tuning closeout — 2026-10-08

本轮五个方向已完成实测和取舍。最终保留上一轮的 resident helper 引擎与配置；本轮没有发现足以替换它的稳定、全面的性能收益。新增的 RAM 副本代码已经撤回，构建目录的程序也恢复到已采用版本。这不表示模型已经没有瓶颈：批量 prefill 的文件来源权重搬运仍然存在。

当前使用 `C:/strata-models/strata-dual-p100-experimental.json` 和 `E:/strata-setup/part2-helper-resident/strata.exe`。主要设置为 `--gpu 0,1 --expert-cache auto --expert-cache-device1 auto --remote-expert-opt --mmap-experts --resident-experts --prefill auto --short-read 448 --spec 4 --spec-min-p 0.8`，关闭动态专家交换，保留 6 GiB 的 resident 内存余量。原专家画像不变。这个双卡配置的上下文上限仍为 **8192**；原单卡 256K 配置没有被替换。

## 硬件与方法

- i7-13850HX，32 GB RAM；2080 Ti 22 GiB / 310 W，P100 16 GiB / 250 W；Windows WDDM，无 P2P。驱动 537.13 未变。
- 2080 Ti 处理主干、KV、输出头和 MTP；P100 处理辅助专家，CPU 处理剩余专家。CPU 专家副本通常为 10.83 GiB，VirtualLock 成功，CUDA pinned DMA 副本为 0 GiB。
- 原始运行证据位于 `E:/strata-setup/part2-tuning`，精简归档位于 `bench/results/2026-10-08-part2-tuning`。共 13 次串行启动，106 个验证请求，另有 3 个独立画像采集请求；未并发运行模型。
- temperature=0、关闭 thinking，使用同一 IQ3_XXS 模型与 INT8 KV。请求耗时包含整个 HTTP 请求，另保存 prompt/decode 时间、输出 token 数、草稿接受数、文件来源计数和 helper 等待时间。模型启动耗时不计入请求耗时。
- 验证包含事实与算术 JSON、Python 去重函数（AST 限制并执行空列表、顺序、字符串和 None 等用例）、928/1924/5107 token 检索、完整 1–60 平方列表、DNS 自由文本和重复提示缓存。106 个响应检查均通过，其中 11 个自由文本响应只做长度/术语基础检查；这不是全面的语义质量评估。重复提示实际复用了 19 个 token。
- baseline-b、baseline-c 和 short1024 在同一进程各重复两轮。大部分筛选候选仅启动一次；没有随机顺序或充分样本，不能据小幅单轮差异声称稳定收益。第二轮不等于模型提示缓存命中：检索任务的 `cache_n` 仍是 0，OS 文件缓存及已初始化状态会影响速度。

## 五个方向的最终取舍

| 方向 | 实测 | 取舍 |
|---|---|---|
| 减少 prefill 文件读取 | 允许 helper 存在时保存主卡借用区域，多锁 2.81 GiB RAM。1924-token 请求累计文件源 blob 数 9994 → 8782，但请求 22.20 → 25.71 秒；RAM 10.83 → 13.64 GiB | 撤回补丁；减少文件源计数没有换来加速 |
| prefill 分块 | 显式 512 / 2048 的单轮 1924-token 请求分别 20.37 / 20.24 秒；原配置初测 22.20 秒，复测随运行阶段和先前请求出现更大变化 | 保留 auto；不把小幅单轮差异写成固定默认值 |
| P100 与 CPU 分工 | helper 降至 6000 专家，RAM 15.34 GiB；318-token 生成从 81.9 降至 65.5 token/s，代码任务基本持平 | 保留 helper auto；把更多工作交给 CPU 没有整体收益 |
| 专家画像 | 3 个独立英/中文与代码训练请求，49392 条路由记录、493920 个专家路由，覆盖 48 层。`make_profile.py --reorder` 生成完整 24576 对排序；代码 96.2 → 108.4 token/s，但 1924-token 请求 28.21 秒，5107-token 请求 26.67 秒 | 保留原画像；新画像只作为实验留存，不作通用默认 |
| MTP | spec2 的318-token任务仅58.0 token/s；spec8代码达到115.3，但同一较长生成80.0，草稿拒绝增多。spec6及0.90/0.95门槛也未提供一致收益；原配置自由文本复测66.5–71.2 token/s | 保留 spec4 / min-p 0.8 |

补测了现有 short-read 路径：将阈值从 448 提到 1024，928-token 首次请求 13.92 → 10.72 秒、专家文件源读取变为 0；第二轮却由 **5.43 → 11.24 秒**。同一轮下一条1924-token请求也由16.76变为24.13秒。因为搬运和文件缓存的成本会被转移到后续请求，最终仍保留448。

这些吞吐量来自各自具体任务；数字序列的草稿接受率远高于自由文本。不能把81.9或115.3 token/s当成通用速度。文件源读取也不等于物理SSD读取，OS可能已经缓存对应页面。

## 代码、回退与合并范围

候选 RAM 借用副本只修改 resident planner 的条件，沿用内存预算；重新构建通过，`file_expert_source_test --rotation-gpu` 包含借用副本/helper 排除/回退字节一致性验证并通过。因为性能回退，候选源代码没有进入最终引擎。补丁与测试日志分别保留在归档的 `rejected-lend.patch`、`source-test.log`，不提交为新的性能 PR。

最终两个程序 `E:/strata-setup/part2-helper-resident/strata.exe` 与 `E:/strata-setup/part2-dual/build/strata.exe` SHA256相同：`7e5f2d45b92b888e910954b3a9b03ac758872cedd8645764af6cf1626ee141b9`。配置 SHA256 为 `360ed3d01dea155e6280b99ef10b672ff9389b94bdda89fa0fee70960d7bfc21`。本轮只新增可复现的 benchmark 工具和证据文档，没有新增生产引擎代码，也没有把本机参数写成上游默认值。

更早的 mmap、layer-split 和单卡配置继续保留。测试服务器已正常停止。未修改旧审计文档中原有的用户编辑。

## 复现

在仓库根目录使用能运行 Strata server 的 Python 环境。每轮保存独立日志、完整响应和实际配置，不修改基准配置；使用空闲本地端口与新 label，串行运行。需要相同模型文件与驱动兼容的可执行程序；归档记录本机路径。

```powershell
python tools/bench_part2_tuning.py baseline-new --config bench/results/2026-10-08-part2-tuning/retained-config.json --out E:/strata-setup/part2-recheck --extended --medium --rounds 2
python tools/bench_part2_tuning.py candidate-new --config bench/results/2026-10-08-part2-tuning/retained-config.json --out E:/strata-setup/part2-recheck --overrides '{"short_read":1024}' --extended --medium --rounds 2
```

`--training` 写入独立 routing trace，`--thresholds` 为 code/decode/prose 追加 0.90、0.95 门槛请求。画像采集与验证请求不同，未使用验证集生成画像。原始 trace 和未采用的画像保存在原始证据目录，其大小与 SHA256 在 receipt 中；大二进制程序和 trace 没有重复提交进仓库。
