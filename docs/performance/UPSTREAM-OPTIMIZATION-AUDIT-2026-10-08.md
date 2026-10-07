# 全仓库优化盘点与最小上游提交

> 2026-10-08 最终结案：已更新上游并提交六个 PR，idle 已移植、验证并恢复日常配置；剩余旧 refill/tile/dispatch 经当前基线筛选不采用。五项待审查，HC 工作区一项草稿。以下旧“剩余待办”和状态以 [最终结案记录](UPSTREAM-CLOSEOUT-2026-10-08.md) 为准。

比较日期：2026-10-08。本地HEAD `8282198`，包含未提交但已日常采用的`src/prefill/prefill.cpp`。最新上游为`d5ea7133741e67743c0e886bb426c0ce8d69cf6c`（0.1.40.3）；本地之前合入的0.1.38为`99f3dbd`。上游本次fetch报告历史重写，不能把不同SHA、ahead数量或旧PR的CLOSED状态当成独有功能或被拒绝的证据。

盘点范围包括fork提交历史、相对原上游的58个源码/构建/测试文件、当前未提交源码、FORK_NOTES、历次性能报告和bench/results实验索引。以技术族归并参数扫描，所有实验变体继续保留在原始索引，不把数百个开关分别包装成创新。旧报告中“日常32K FP16”“未采用”等文字有时间范围，最新日常为256K普通INT8、32K prefill。

## 把全部技术简化成五件事

1. **少搬数据**：专家驻留、画像、直接/缓存文件读取、补回、复用临时显存。
2. **少重复计算**：共享历史和分词复用、更大的有效prefill分块、跨token重用权重解码。
3. **让工作重叠**：CPU/GPU分工、ring流水线、PLE读预取、异步状态提交。
4. **减少空间占用**：KV量化、按需host缓冲、工作区生命周期复用、空闲状态卸载。
5. **降低单步成本**：适配sm75的attention/GEMM、Top-K/scorer、融合kernel和CPU SIMD。

这些是工程手段，不都是本fork原创。硬件修复和调参不是可提交的通用引擎算法；各轮不同模型/功耗/PCIe/上下文条件的收益不能相加。

## 全部技术族的来源与处置

| 技术族 | 本地证据/实现入口 | 对最新上游的判断 | 最简提交处置 |
|---|---|---|---|
| sm75 Turing、Volta构建及attention回退 | FORK_NOTES；旧#87/#130；qsa_prompt_attn | 上游已有对应支持，来源包含社区工作 | 不重提整套端口 |
| 低RAM三级专家源、Windows mmap/pinned/文件读取 | tiered_source.cpp；旧#80/#362；expert_source.hpp | 上游FileExpertSource已有文件/RAM/VRAM路径，具体接口已重构；不等于本地912行可直接移植 | 仅保留差异研究，禁止整文件覆盖 |
| DMA能力、部分注册边界bounce、冷预取去重和释放重复映射 | 90f67ea、c23811a；expert_cache.cpp | 本地有特定修正；上游源/arena设计不同，旧补丁的触发条件须重新定位 | 不附带到性能PR；若仍有缺陷再给独立复现 |
| 按实际亲和性选CPU、P/E核与任务切分 | pool.cpp；e287ed0；CPU系列报告 | 上游已有pool_affinity_win/linux及pool-tasks；本地历史修正不能直接按SHA认领 | 不移植旧pool实现；P-only本机更慢 |
| AVX-VNNI Q2与IQ格式整数点积 | 2a52779；q2_rows_impl；IQ3S报告 | 上游q2_avx2_rows.inl、iq_avx2_rows.inl及运行时检测已覆盖 | 无新通用收益，不提交旧开关副本 |
| 原生IQ3/IQ2与Q4_0/Q8_0 MMQ、减少升位 | iq_pack、requant_gsq、真实块探针 | 上游支持持续扩展；早期“坏内核”结论已撤回 | 不提交过时强制升位策略，探针仅研究工具 |
| 专家画像与成本/混合画像 | make_profile；decode10资产 | 上游已有画像生成/驻留；特定画像是本机训练资产 | 不提交个人画像二进制 |
| MTP窗口、min-p与草稿词表 | decode10；draft_vocab；配置快照 | 上游已有机制；88252词表和参数是工作负载选择，部分输出改变 | 不把+11.13%组合归因成单个新kernel |
| GPU decode融合、tile、IQ3_S跨token权重解码重用 | verify、fused_gr、native_mmvq；tuning31 | 上游有自身融合/分支，但本地gr_norm_stream_kernel、gr_down_tile_kernel、fused_gr_read_multi_local在main不存在；不能说这些实现已被完整吸收 | 属于剩余独有实现；需从tuning31组合中拆出单项并与新上游单独比较，不能用旧+11.13%组合证明残余内核收益 |
| 空PCIe分支、原生预测、专家放置、调度 | verify；empty-PCIe、native-prediction、placement报告 | 部分为本地实验，许多没有稳定端到端收益；上游已有plan/pipeline更新 | 不发布未采用组合 |
| 异步commit | 社区#284；verify.cpp | 上游已有set_commit_async/wait_commit且默认单GPU启用 | 记来源，不重提 |
| Turing prompt attention | 社区#270；qsa_prompt_attn | 上游已有sm75相关路径 | 不重提 |
| 首块PLE读与layer0重叠 | 社区#374；prefill.cpp | 上游已在layer0旁启动ple_next | 不重提 |
| 专家补回、4线程双pinned缓冲、cached overlapped reads | expert_cache::fill_slots_staged；generate；refill报告 | 本地具体实现独立；上游loan/refill/文件源已大幅更新，存在等价目标 | 不搬旧接口；本机旧收益不是最新上游收益 |
| ring192/large384、prefill16K/32K | prefill；prefill-cache/loading报告 | 上游有ring与prefill auto，具体阈值不同；本机配置不通用 | 参数不进默认PR |
| 活动块Top-K、33/65寄存器分支 | qsa_select；prefill5报告 | 上游已有reach/count-based分支与sm75宽核 | 不重提过时实现 |
| scorer每key多query复用 | qsa_select；prefill_scores_test | 上游已有WQT以及sm75 tiled SGEMM等实现 | 不重提 |
| BF16经精确FP16缩放的sm75 GEMM | gemm.cu；prefill_bf16_test | 本地实验关闭；输入可精确转换不保证累加顺序相同，上游另有GEMM路线 | 不作为bit-exact采用项 |
| 根检查点512、短尾448、历史KV复用 | generate；prefill-cache报告 | 上游已有prompt-cache-root/short-read；具体阈值是本机选择 | 不重复功能或强改默认 |
| 增量分词：只重编共享特殊token边界后的尾巴 | 5373d47；INCREMENTAL-PROMPT报告 | 最新main没有；核心参考社区#gputier的#567（见下文） | 本地适配保留为补充，不冒充原创/重复抢提 |
| 空闲session落盘、TTL、释放GPU状态与CPU检查点 | idle_cache.cpp；docs/idle-cache.md | 本地具体生命周期仍独立；上游已有conversation_file持久化及server idle unload，语义不同 | 可独立设计PR，但非小补丁；本次不把旧generate生命周期整体移植 |
| PLE host按需分配、单chunk仅一个缓冲 | 当前未提交prefill；PLE-DEMAND/SINGLE-HOST报告 | 上游仍在init预分配两份最大host缓冲 | **首个最小PR：只做这项**；移除本地两个实验开关和计时日志，沿用上游pageable fallback |
| HC与GDN/QSA/MoE工作区复用；emb与bo别名 | 当前未提交prefill；32K报告 | 上游仍独立分配对应空间，但新增next-layer norm融合会改变活跃区间 | 本地已采用；最新上游不能直接套旧别名证明，单独保存，不混入PLE PR |
| 修正bytes_needed与实际carve对齐 | 当前prefill；HC报告 | 上游布局已有变化，且存在#1283相关PR | 逐布局复核后独立修复；不是整套固定内存账本移植 |
| MoE GU/H借down输出空间、in-place SwiGLU | 私有moe-inplace/chunk-select；组件与质量报告 | 本地候选，main没有这套组合；尚未日常采用 | 已结案暂缓，保留补丁，不重新启动验证 |
| shared gate tile与请求级32K/40K选择 | 私有gate-tile/chunk-select；两会话报告 | 本地候选；37K收益可靠，但首次READY非劣性未证，其他长度不普遍 | 已结案暂缓，不包装成生产默认 |
| 层边界取消及清理 | 私有chunk-layer-cancel及state/checkpoint报告 | 本地候选；有重读代价和未测路径 | 已结案暂缓，不顺带提交 |
| Python取消poll 250ms | 私有chunk-cancel-poll | 上游423f589已提供500ms取消轮询 | 不重复提交，250ms不是独立新算法 |
| INT8/Hadamard/Q4/K8V4及长上下文容量 | KV系列报告 | KV格式机制为上游已有；本地主要是容量、质量与场景选择验证 | 提供测量结论，不能申领格式原创 |
| parked/checkpoint转移、尾部补齐、可见边界 | checkpoint-transfer、MTP-lineage、visible-tail等 | 本地实验存在严格状态不一致或未证收益，HOLD保持 | 不提交未资格化路径 |
| CPU冷缓冲、gather、页预热、预取提前、busy-spin/padding | CPU/prefetch/stager系列 | 很多负结果；上游另有stager sleep、CPU-share和IQ3_S改进 | 不把负实验开关堆入PR |
| GDN prefix/GR barrier/dependency resident、kernel重排 | prefix/gdn/gr-barrier系列 | 本地研究与筛选，不是全部已采用 | 原始结果留档，无证据不推进生产补丁 |
| VTune/CUPTI、CPU周期、逻辑供应字节、状态hash、模型质量/NLL、生命周期审计 | bench/results、硬件与性能报告 | 测量方法与验证资产，非用户执行路径优化 | 每个PR只附与改动有关的可复现实验和最小测试 |
| PCIe×4→×16、功耗/频率、稳定性、程序所在磁盘 | 硬件报告、STARTUP-FACTOR | 硬件/环境修复，不是源码技术 | 作为实验条件，不计入PR算法收益 |

## 社区来源不能省略

已核对[#567](https://github.com/Niko1221/Strata/pull/567)：作者gputier，最新head `76b916e2b54584e1b8f169874d71490a74175245`。维护者说明关闭来自main历史重写，不是拒绝；该PR后续版本已处理plain spans。本地0.1.38采用的是更早算法加缓存边界、完全命中与服务适配。此次0.1.40.3本地准备版本对带literal spans的请求保持上游完整编码，避免改变#537/#931语义，且有独立回归。它是相关作者工作的补充/替代适配，非新增原创算法；优先向原PR提供测试与实际词表证据，不发重复功能PR。

## 最小化规则与PR划分

- 以最新main建立干净分支，不能从本地fork直接向上游开整分支PR：它含旧历史、个人路径、测试资产、OBJ和过时接口。
- 第一份补丁只改变PLE host缓冲生命周期；不改chunk默认、显存布局、数学kernel、模型配置、采样或量化。它可独立审查，不能使用整套32K组合的22.8%–32.5%收益为自己背书。
- 分词复用另存一个本地review分支/patch，明确来源和plain-span回退。不与PLE捆绑。
- 工作区别名、空闲状态落盘、Windows补回按独立模块保留；对最新main的依赖和语义未闭合时不声称ready-to-merge。
- 暂缓的40K/取消/检查点等实验维持结案，准备PR不是自动重新启动全套性能测试的授权。
- 历史测量只证明旧fork上的结果。移植到0.1.40.3后新增的组件/回归测试与尚缺的整模型验证必须单列。

原始综述：[OPTIMIZATION-SUMMARY](OPTIMIZATION-SUMMARY.md)、[FORK_NOTES](../../FORK_NOTES.md)、[筛选索引](../../bench/results/2026-10-03-local-optimization/SCREENING-INDEX.md)、[本轮结案](CHUNK-OPTIMIZATION-CLOSEOUT-2026-10-08.md)。这些索引中的历史待办不自动成为本次PR范围。

## 本次交付状态

后续用户已授权逐项发布。最新状态见 [上游 PR 提交记录](UPSTREAM-PR-BATCH-2026-10-08.md)：#1451、#1454、#1455、#1457 均已提交为独立草稿；分词最终联合 273 项通过。下面关于“仅本地 review”的描述记录发布前状态，已由此更新取代；来源归属和未验证范围不变。

58个历史源码/构建/测试文件与108份性能报告的清单、源码哈希和提交候选列表已写入`bench/results/2026-10-08-upstream-pr-preparation/inventory.json`。清单本身不证明语义等价；上表给出已核对的技术判断，不能把“实现不同”误写成“上游没有这类能力”。

最小PLE分支在`C:/Users/Winge/Documents/Playground/Strata-optimization-pr`，基于精确最新main，独立于日常树。真实CUDA测试64例通过；CMake/Ninja构建及CTest再次通过；prefill.cpp的普通与native/MMQ宏两种编译均通过。未重新运行完整模型、未完成其他GPU后端验证，因此这是可审查的PR候选，不是已经证明所有后端无回归或已经日常采用的0.1.40.3版本。

分词补充分支`codex/prompt-reuse-review`，提交`94befce`。现有server的262项在联合测试中无失败；新测试最初有1个“确实跳过前缀”的夹具错误：只有尾部end marker，安全margin会合法地回读长文本。加上真实assistant历史后，11项新增测试全部通过；原始273项联合运行的1项失败不抹去。这个分支是有来源说明的本地review材料，不是已发布PR。
