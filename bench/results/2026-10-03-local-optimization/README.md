# 本机优化结果包（2026-10-03）

先读 [总总结](../../../docs/performance/OPTIMIZATION-SUMMARY.md)。所有数值都有阶段和测试口径；不能将不同文件的最好成绩拼成一个版本。

## 内容

- `screens/`：55 份根目录筛选/诊断汇总，详见 [SCREENING-INDEX.md](SCREENING-INDEX.md)。含负结果和早期探索，不统一视为正式确认。
- `outputs/`：各阶段发布过的 JSON 摘要、配置与验证清单。
- `community/`、`community2/`、`agent-prefill/`、`cache-idle/`、`context256/`、`prefill3/4/5/`：存在的各轮小型汇总/QA。最新轮次保留全部根目录 JSON，以及针对性测试结果文本。
- `assets/expert-profile.bin`：最终混合静态画像，196632 字节。
- `assets/draft_vocab.bin`：88252 项 MTP 草稿词表，353008 字节。它是词表 ID 数据，不是模型权重。
- `current-config.snapshot.json`：当前本机配置的路径脱敏快照；`current-config.example.json`：待填路径的运行示例。
- `manifest.json`：180 份复制材料的原始和发布 SHA-256。路径替换、JSON 排版、报告历史提示会改变发布哈希，性能数字未重算。生成的总总结/索引/示例/验证文件本身不在该复制清单内，由 Git 跟踪。
- `publication-validation.json`：本次 40 项 mock 服务测试、236 文件哈希核对、已验证 exe 哈希、只读服务状态。

原报告在 [archive](../../../docs/performance/archive/)；本文用 `<TASK>`、`<REPO>`、`<USER_HOME>` 替换个人工作区前缀。旧附件名、日志引用和源文件路径是历史记录；部分原件仅留本机。**本包不是包含模型和所有输入的独立可执行基准套件**。没有上传大型提示正文、模型、历史二进制、KV 快照、完整转储和大型 ZIP。

## 运行当前配置

1. 使用本提交构建的引擎，并准备同一 IQ3_XXS 原生 pack、tokenizer、原 GGUF 两个分片和对应 MTP 权重。分片不能因为已打包就删除。
2. 复制示例 JSON 到本机配置位置，替换所有 `<REPO>`、`<MODEL_ROOT>`、`<CUDA_ROOT>` 占位符。示例不是自动展开环境变量的模板。
3. 示例 `--expert-profile` 指向本包画像。创建单独的 `<MODEL_ROOT>/decode10/mtp` 目录，复用本模型已有 MTP 文件，再将本包 `draft_vocab.bin` 放入该目录。原 MTP dense/experts 权重不修改；不要与其它模型混用这个词表或画像。
4. 保持 `--max-context 32768`，FP16 KV，单服务实例。各开关显式写在示例中，单独运行裸 exe 不保证得到相同组合。
5. 在仓库根目录以 `python -m serve.server --config <配置文件路径> --host 127.0.0.1 --port 8080` 启动。若本机已有服务运行，不再启动第二份占用 GPU。

构建环境：Windows / Ninja / VS2022 MSVC 19.44 / CUDA 12.4。本机 CMake cache 使用 `CMAKE_BUILD_TYPE=Release`、`CMAKE_CUDA_ARCHITECTURES=75`、`CMAKE_CUDA_RUNTIME_LIBRARY=Shared`，并指定便携 nvcc 路径。CUDA 12.4 配此 MSVC 使用 `-allow-unsupported-compiler`；运行时需让 CUDA bin 中 DLL 可见。详见 [FORK_NOTES 构建记录](../../../FORK_NOTES.md)。ggml 固定提交为 `3cf03257f219afbe7334045ff7c6a06ac68c627d`，可由仓库固定版本取得或通过 `STRATA_GGML_DIR` 指向该版本 checkout。

## 如何重做可信对照

为每个候选保留真实旧/新 exe、完整参数和 SHA-256；请求串行，正式计时关闭 profiling/TRACE/额外字节核验，期间不编译或跑微基准。完整 Prefill 逐次确认 `cache_n=0`；首次和重复分开，另测真实缓存命中。按 ABBA 或顺序平衡的多轮测试，保留慢样本，并分别记录 TTFT、prompt_ms 和 Decode。

复测不能只复制单个历史 JSON：阶段间的画像、GPU 稳定状态、PCIe 链路、KV 容量和文件缓存条件不同。旧阶段的具体请求/轮次以对应报告为准，完整原始复现材料留在本机证据 ZIP。最新最终组合 HC-off 只有一次额外 128K 无诊断验证，261K 未补测；请勿把三项全开的候选表当作最终配置保证。

本次发布只重跑不使用 GPU 的 `python -m unittest serve.test_server -q`（40/40）。先前的 CUDA/数值、缓存回归与长输入性能结果均明确标为历史验证；没有为了发布中断日常服务。
