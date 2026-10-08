# Part2：2080 Ti + P100 接入与第一轮基线（2026-10-08）

## 当前结论

两张卡均已恢复至 537.13，Windows 设备错误码均为 0。CUDA 实际分配、内核执行和结果读回均通过：GPU0 RTX 2080 Ti 22 GiB / sm75；GPU1 P100 16 GiB / sm60。本轮没有安装或修改驱动。两卡均为 WDDM，P2P 不可用；PCIe 分别为 3.0 x16、3.0 x4，功耗上限均为 250W。之前 2080 Ti 的 310W/560.94 测量不能直接作为新性能基线。

使用 Part1 六项优化整合源码 4ea4a54，编译独立 CUDA 12.4.131 实验版：STRATA_EXPERIMENTAL_SM60=ON，60-real;75-real，仅生成本机两种 cubin。简单 CUDA 探针及真实模型均能在 537.13 上运行，不要求升级驱动。源码未作更改，重用上游 Pascal 与多卡实现。完整构建和日志在 E:/strata-setup/part2-dual。

## 服务基线

IQ3_XXS、INT8 KV、4096 context、prefill 128、MTP spec4、resident budget 8 GiB、pcie-frac 0。每次启动先检查 2+2 首次/重复请求，再读 268-token 提示并生成 31 tokens（重复 apple 30 次）；七次服务运行均检查通过并正常退出，P100/2080 Ti 的 HC 启动逐位自检通过。

| 模式 | 提示处理秒数 | 解码 token/s |
|---|---:|---:|
| single | 51.38 | 7.0 |
| single-r2 | 53.35 | 7.0 |
| dual-forward | 51.24 | 7.4 |
| dual-reverse | 48.29 | 7.6 |
| dual-fixed28 | 16.58 | 38.9 |
| dual-fixed28-r2 | 17.39 | 36.5 |
| dual-coverage | 17.62 | 36.3 |

单卡及固定 28 层各测两次，其余各一次。短生成、预热顺序和系统内存影响仍存在；不是正式长上下文 benchmark，也没有证明不同分层逐位等价或所有请求提速。GPU expert 路由/计算位置变化可能改变舍入。固定 28 层的 workload GPU expert 命中率为 69.1%，单卡 31.6%。

首次离线双卡 CLI 试跑被参数校验拒绝，因为 layer-split 需要 --serve；后续全部改用真实 HTTP 服务，不能把那个失败算成 GPU 不兼容。

## 首个优化方向：自动分层的命中率估算

默认 auto 在 0,1 顺序选 K=47，P100 只跑最后一层，驻留约 1.04 GiB 专家；反向顺序选 K=2，P100 只跑前两层。源码 generate.cpp 中双/三卡仍使用 (rank+1)^-1.2 的旧拟合，日志预测约 97% routed mass，但本轮实际命中远低于它。不能用该估算把未利用显存的代价视作很小。

上游已有 STRATA_SPLIT_COVER_B：设置 3 即在双卡也使用 held-fraction coverage curve，auto 在本机选 K=32，P100 驻留约 9.08 GiB 专家。本次正确性检查通过，表现接近手工 K=28。它仍是经验曲线，不是已证明对所有机器最优的自动算法；暂不修改上游默认或提交新的性能 PR。

独立实验配置：C:/strata-models/strata-dual-p100-experimental.json，gpu=[0,1]、layer_split=auto、STRATA_SPLIT_COVER_B=3，使用 E:/strata-setup/part2-dual/build/strata.exe。当前验证容量只有 4096。现有单卡 256K 日常配置及二进制保留。双卡配置不启用 Part1 的 session idle offload，因为该功能目前明确只支持单卡。

## 后续范围

Part2 的硬件接入和首次服务基线完成；长期性能优化尚未完成。下一步应扩大提示长度/上下文、请求类型与重复 A/B，再判断覆盖率估算是否值得泛化；不要把这次短请求的约五倍 decode 差距外推为整体日常提速。跨卡 KV/取消/长上下文和多轮聊天尚未专项验证，32K/256K 双卡配置未通过资格化。本轮无后台模型残留，也没有恢复旧无限扫描。

紧凑结果、完整 HTTP 结果和复现脚本在 bench/results/2026-10-08-part2-dual；各次 engine/server 日志、编译日志、配置保存在 E:/strata-setup/part2-dual。summary.json 记录 exe/config SHA256。
