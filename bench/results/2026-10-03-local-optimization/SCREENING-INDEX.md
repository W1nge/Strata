# 历史参数筛选索引

以下完整列出根目录 55 份筛选/诊断摘要。数值沿用各文件原来的统计口径；不跨文件排名，不把初筛或失败扫描当作最终收益。正式采用决定见总总结和各轮报告。

## benchmark_summary

[完整 JSON](screens/benchmark_summary.json)

诊断/汇总结构：`列表，4 条`。详细数值见 JSON。

## decode10_broad_screen_summary

[完整 JSON](screens/decode10_broad_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| subset_p8 | 18 | 66.0721 |
| subset_p9 | 18 | 65.5399 |

## decode10_cache_baseA_screen_summary

[完整 JSON](screens/decode10_cache_baseA_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 12 | 58.9452 |
| gpu15 | 12 | 61.0570 |

## decode10_cache_conservative_screen_summary

[完整 JSON](screens/decode10_cache_conservative_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu15 | 12 | 62.9620 |

## decode10_cache_cost_screen_summary

[完整 JSON](screens/decode10_cache_cost_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu15 | 12 | 61.5903 |

## decode10_cache_mix_screen_summary

[完整 JSON](screens/decode10_cache_mix_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu15 | 12 | 61.3922 |

## decode10_candidate_confirm_summary

[完整 JSON](screens/decode10_candidate_confirm_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| candidate | 42 | 67.1314 |

## decode10_conservative31_screen_summary

[完整 JSON](screens/decode10_conservative31_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu31 | 18 | 63.7043 |

## decode10_dense_full_screen_summary

[完整 JSON](screens/decode10_dense_full_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 18 | 59.3414 |
| gpu15 | 18 | 60.9740 |
| gpu31 | 18 | 61.0932 |

## decode10_draft_broad_summary

[完整 JSON](screens/decode10_draft_broad_summary.json)

诊断/汇总结构：`tokens, full_vocab, cjk_tokens, training_tokens, training_distinct, selection, target_vocab_unchanged, path`。详细数值见 JSON。

## decode10_draft_vocab_summary

[完整 JSON](screens/decode10_draft_vocab_summary.json)

诊断/汇总结构：`tokens, full_vocab, single_cjk_tokens, training_tokens, training_distinct, selection, target_vocab_unchanged, path`。详细数值见 JSON。

## decode10_gpu_screen_summary

[完整 JSON](screens/decode10_gpu_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 58.3500 |
| hc_single | 24 | 58.9565 |
| hc_tile | 24 | 59.1471 |
| hc_both | 24 | 59.3319 |
| hc_fuse | 24 | 59.4789 |

## decode10_original_return_screen_summary

[完整 JSON](screens/decode10_original_return_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 42 | 60.4068 |

## decode10_pad1_screen_summary

[完整 JSON](screens/decode10_pad1_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu31 | 12 | 61.2593 |
| gpu31_m6 | 12 | 61.0578 |
| gpu31_m4 | 12 | 59.0035 |

## decode10_profile_http_summary

[完整 JSON](screens/decode10_profile_http_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 6 | 60.5680 |

## decode10_profile_summary

[完整 JSON](screens/decode10_profile_summary.json)

诊断/汇总结构：`source, requests, all, first, later`。详细数值见 JSON。

## decode10_profiles_summary

[完整 JSON](screens/decode10_profiles_summary.json)

诊断/汇总结构：`records, entries, distinct, cpu_worker_ms_per_expert, profiles`。详细数值见 JSON。

## decode10_round2_screen_summary

[完整 JSON](screens/decode10_round2_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 12 | 62.7904 |
| gpu15 | 12 | 64.5566 |
| shrink12 | 12 | 64.7422 |
| gentle12 | 12 | 64.5994 |
| shrink6 | 12 | 64.7231 |

## decode10_subset_screen_summary

[完整 JSON](screens/decode10_subset_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| subset_p8 | 18 | 63.7846 |
| subset_p9 | 18 | 64.3907 |

## decode10_training_http_summary

[完整 JSON](screens/decode10_training_http_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| gpu15 | 16 | 46.5781 |

## empty_pcie_ab_summary

[完整 JSON](screens/empty_pcie_ab_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| full | 24 | 52.3901 |
| skip | 24 | 45.9682 |

## empty_pcie_exploratory_summary

[完整 JSON](screens/empty_pcie_exploratory_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| full | 24 | 52.6587 |
| skip | 24 | 52.4158 |

## joint_profile_summary

[完整 JSON](screens/joint_profile_summary.json)

诊断/汇总结构：`source, requests, all, first, later`。详细数值见 JSON。

## pcie_control_verified_summary

[完整 JSON](screens/pcie_control_verified_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| full | 24 | 52.3901 |
| skip | 24 | 45.9682 |

## x16_adapt16_long_screen_summary

[完整 JSON](screens/x16_adapt16_long_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 96 | 55.8407 |

## x16_adapt16_screen_summary

[完整 JSON](screens/x16_adapt16_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 54.3656 |

## x16_adapt4_screen_summary

[完整 JSON](screens/x16_adapt4_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 40.2531 |

## x16_budget6_screen_summary

[完整 JSON](screens/x16_budget6_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 58.3706 |

## x16_budget8_screen_summary

[完整 JSON](screens/x16_budget8_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 58.4088 |

## x16_compute_suite_summary

[完整 JSON](screens/x16_compute_suite_summary.json)

诊断/汇总结构：`note, cases`。详细数值见 JSON。

## x16_cpu_best_screen_summary

[完整 JSON](screens/x16_cpu_best_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 12 | 61.2436 |
| tasks3 | 12 | 59.9930 |
| tasks6 | 12 | 60.9104 |
| tasks16 | 12 | 61.2563 |
| nt1_iq2xxs | 12 | 61.5713 |
| nt1_iq2xs | 12 | 61.4560 |
| nt1_iq3s | 12 | 61.7236 |
| nt1_all | 12 | 61.4236 |

## x16_cpu_screen_summary

[完整 JSON](screens/x16_cpu_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 12 | 59.8121 |
| tasks1 | 12 | 56.6042 |
| tasks6 | 12 | 61.3990 |
| tasks12 | 12 | 61.9003 |
| tasks16 | 12 | 61.6813 |
| pinned_first | 12 | 59.9691 |
| nt_first | 12 | 59.3889 |
| pinned_nt_first | 12 | 60.5321 |
| nt1_iq2xxs | 12 | 60.2352 |
| nt1_iq2xs | 12 | 59.9235 |
| nt1_iq3s | 12 | 59.9078 |
| nt1_all3 | 12 | 58.9620 |

## x16_direct_screen_summary

[完整 JSON](screens/x16_direct_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| cpu | 12 | 57.2154 |
| p125 | 12 | 57.6798 |
| p25 | 12 | 57.8116 |
| p50 | 12 | 49.5235 |
| p75 | 12 | 43.7084 |
| p100 | 12 | 34.0884 |

## x16_dma_best_screen_summary

[完整 JSON](screens/x16_dma_best_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 57.6278 |
| frac0625 | 24 | 58.4611 |
| frac125 | 24 | 58.3356 |
| frac25 | 24 | 57.4065 |

## x16_dma_confirm_screen_summary

[完整 JSON](screens/x16_dma_confirm_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 48 | 58.5373 |
| frac0625 | 48 | 57.5762 |
| frac125 | 48 | 58.1369 |

## x16_dma_screen_summary

[完整 JSON](screens/x16_dma_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| cpu | 12 | 56.7211 |
| p125 | 12 | 57.8461 |
| p25 | 12 | 59.8146 |
| p50 | 12 | 52.1872 |
| p75 | 12 | 47.7996 |
| p100 | 12 | 37.6747 |

## x16_final_fresh_screen_summary

[完整 JSON](screens/x16_final_fresh_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| original | 24 | 54.6825 |
| baseline | 24 | 58.1959 |
| skip | 24 | 59.3596 |

## x16_followup_suite_summary

[完整 JSON](screens/x16_followup_suite_summary.json)

诊断/汇总结构：`note, cases`。详细数值见 JSON。

## x16_fresh_confirm_summary

[完整 JSON](screens/x16_fresh_confirm_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 18 | 54.7380 |
| candidate | 18 | 58.1948 |

## x16_kernel_screen_summary

[完整 JSON](screens/x16_kernel_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| cpu | 12 | 55.9393 |
| p125 | 12 | 61.2890 |
| p25 | 12 | 51.5483 |
| p50 | 12 | 49.8980 |
| p75 | 12 | 38.4522 |
| p100 | 12 | 41.7898 |

## x16_memory_suite_summary

[完整 JSON](screens/x16_memory_suite_summary.json)

诊断/汇总结构：`note, cases`。详细数值见 JSON。

## x16_mtp2_screen_summary

[完整 JSON](screens/x16_mtp2_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| m0 | 36 | 50.3994 |
| m2 | 36 | 51.4527 |
| baseline | 36 | 54.3754 |
| m6 | 36 | 56.9077 |
| m8 | 36 | 57.5237 |

## x16_mtp_refine_summary

[完整 JSON](screens/x16_mtp_refine_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| p6 | 36 | 57.4598 |
| p7 | 36 | 58.2982 |
| baseline | 36 | 58.0162 |
| p9 | 36 | 56.9106 |
| t6p8 | 36 | 58.4329 |
| t6p6 | 36 | 56.4497 |

## x16_order_best_screen_summary

[完整 JSON](screens/x16_order_best_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 12 | 62.7338 |
| pinned_first | 12 | 62.8952 |
| nt_first | 12 | 62.5169 |
| pinned_nt_first | 12 | 62.7712 |

## x16_pf12_screen_summary

[完整 JSON](screens/x16_pf12_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 57.5930 |

## x16_pf16_screen_summary

[完整 JSON](screens/x16_pf16_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 57.3596 |

## x16_pfoff_screen_summary

[完整 JSON](screens/x16_pfoff_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 24 | 59.0180 |

## x16_plan_audit_pairs_summary

[完整 JSON](screens/x16_plan_audit_pairs_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 96 | 51.3379 |
| tasks12 | 96 | 52.0945 |

## x16_plan_audit_repro_summary

[完整 JSON](screens/x16_plan_audit_repro_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 120 | 51.3677 |

## x16_skip_best_screen_summary

[完整 JSON](screens/x16_skip_best_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 58.5576 |
| skip | 36 | 59.4088 |

## x16_stable_cpu_confirm_summary

[完整 JSON](screens/x16_stable_cpu_confirm_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 72 | 53.7307 |
| tasks12 | 72 | 55.0241 |

## x16_static_after_screen_summary

[完整 JSON](screens/x16_static_after_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 58.5707 |

## x16_static_control_screen_summary

[完整 JSON](screens/x16_static_control_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 58.6452 |

## x16_vnni_best_screen_summary

[完整 JSON](screens/x16_vnni_best_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 58.5727 |

## x16_window8_screen_summary

[完整 JSON](screens/x16_window8_screen_summary.json)

| 变体 | 请求数 | Decode tok/s |
|---|---:|---:|
| baseline | 36 | 58.8421 |
| t6 | 36 | 58.0818 |
| t8 | 36 | 57.6137 |
