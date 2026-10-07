# 上游优化贡献结案（2026-10-08）

本轮任务是更新上游、盘点整个仓库、简化并提交有依据的优化，已完成。不是宣称性能已达到理论极限，也不意味着上游已经合并。此前更新记录中的三类待办由本文逐项关闭；不再自动重启历史性能扫描。

## 发布与安装

重新 fetch 后上游仍为 v0.1.40.3 / `d5ea7133741e67743c0e886bb426c0ce8d69cf6c`。日常源码已整合六项优化，源码提交 `3cdda788b799baa0b9802dd71352a805e10f9ec1`，分支 `codex/daily-upstream-01403` 已推送。最终文档提交在其后，不改变程序。

| PR | 内容 | 本轮结束时状态 |
|---|---|---|
| [1451](https://github.com/Niko1221/Strata/pull/1451) | PLE host 按需分配 | OPEN，待审查 |
| [1454](https://github.com/Niko1221/Strata/pull/1454) | embedding 存储复用 | OPEN，待审查 |
| [1455](https://github.com/Niko1221/Strata/pull/1455) | 安全边界分词复用，注明 gputier/#567 来源 | OPEN，待审查 |
| [1457](https://github.com/Niko1221/Strata/pull/1457) | HC read 共享工作区 | OPEN，草稿；padding/control-vector/multi-GPU/non-CUDA 运行覆盖仍不足 |
| [1465](https://github.com/Niko1221/Strata/pull/1465) | norm 保留中间乘积，减少重复读取 | OPEN，待审查 |
| [1471](https://github.com/Niko1221/Strata/pull/1471) | 保留权重的空闲 session 卸载与恢复 | OPEN，待审查 |

GitHub 查询六个 PR 均无合并冲突；这不等于维护者批准。跨硬件覆盖不足明确写在 PR 中，不以本机测试代替。没有提交重复的整套旧 fork、固定硬件参数或自动调参框架。

日常 exe 已替换为整合构建，256K INT8 配置恢复 `--cache-idle-seconds 180 --cache-expire-seconds 3600 --cache-disk-dir E:/strata-setup/idle-session-cache`。这是新格式独立目录，不复用旧 snapshot。功能默认关闭，支持单 CUDA VMM GPU/fully-resident KV，其他不支持组合明确拒绝。写失败保留内存，损坏或过期重读 prompt；显存重新映射失败会结束引擎。

## 剩余候选的最终处置

**旧 HC 单 token 特判和 1280/4-warp down：不提交。** 在 RTX 2080 Ti 上对照当前 staged 路径及已提交 norm 复用，CUDA graph 排除 CPU 发射开销，T=1..8、pending write 开/关、每项五个样本。沿用上游随机 selftest 逐位核对所有输出。四 warp 全部慢于 staged；例如 T=4 无 pending write，62.28 对 52.21 us；T=8 为 130.52 对 102.43 us。单 token 旧特判为 35.75/40.41 us，staged 为 33.18/34.35 us。保留上游调度，删除“继续移植旧 tuning bitmask”的待办。没有整模型收益主张。

**旧四线程、双 pinned 缓冲专家补回：不提交，归档。** 对实际映射文件中预热的数据做七轮交错传输对照，完整 D2H 字节核对通过；计入创建线程、分配 pinned 缓冲和回收的成本。每槽 1,868,800 字节，16/189/512 槽的 queued 中位数为 2.52/29.71/80.60 ms，staged 为 6.40/32.76/82.20 ms。没有独立收益，增加生命周期与错误处理代码不符合本轮简洁易合并目标。此测试只筛选传输机制，不是冷盘或完整 FileExpertSource 的模型测试；没有据此断言所有冷盘场景都无收益。社区 #1237/#1323 的 pinned/批量读取仍在审查，不另造同类生产开关。

**空闲卸载：完成移植、发布和日常恢复。** 重用上游 VmmRange，保存当前 checkpoint 的 dead/block_pos 等新字段，校验快照及过期时间，恢复固定地址和新会话必要常量；实际功能与测试在 #1471。

## 验证与范围

- 完整整合构建通过；native idle_cache_test 通过，包括 CUDA graph remap 后回放、三轮精确恢复、常量、损坏/截断/缺失/过期文件和清理。
- idle 独立分支两轮真实 HTTP 生命周期通过，六项整合版再次通过：落盘、恢复命中、损坏回退、过期回退、流式取消后重新落盘与成功请求。使用 IQ3_XXS、INT8 KV、MTP、4096 context。
- 日常 256K 容量配置首次/重复短请求均回答 4，正常停止。没有测满 256K prompt，也没有在最终 256K 容量下等待完整落盘周期。
- 前轮四模式八次模型对照、PLE 64 例与 norm 逐位验证仍有效；本轮没有改动其数学计算。
- 最终 Python 联合回归 274 项通过（76.397 秒），日志见 bench/results/2026-10-08-upstream-closeout/final-server-tests.log。一次命令误写不存在的 test_prompt_reuse 模块产生 loader error，已改为实际的 test_prompt_encoder 并重跑；不把该次失败报告为通过。

## 证据和回退

可提交的紧凑结果在 `bench/results/2026-10-08-upstream-closeout/`：results.json、两个传输/内核日志、lifecycle.json、http-smoke.json、最终 Python 日志与 probe-hashes.json。原始可执行探针和完整运行日志保存在 `E:/strata-setup/upstream-01403-integrated/`；真实 idle 整合证据在 `E:/strata-setup/integrated-idle-evidence/`。

安装回执 `E:/strata-setup/upstream-01403-integrated/final-install.json` 记录源码及 exe/config SHA256。添加 idle 前的 exe/config 保存在 rollback-01403-before-idle；旧 0.1.38 的 exe/config 仍在 rollback-0138，源码在 codex/pre-01403-daily-snapshot / 4090154。历史未跟踪实验和旧分支未清理。

全仓库 58 个历史源码/构建/测试文件及 108 份报告的技术来源和筛选结论，继续参见 UPSTREAM-OPTIMIZATION-AUDIT-2026-10-08.md；上游已覆盖、个人画像、负实验及先前结案的 40K/取消/检查点研究维持原处置。本轮没有尚待实施的候选；草稿 PR 的额外硬件资格验证属于已公开限制，不能称为全面验证。
