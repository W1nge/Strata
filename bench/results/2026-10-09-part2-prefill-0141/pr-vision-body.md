`test_vision_device` expects the engine to keep GPU order `0,1`, but 0.1.41's automatic ordering can return `1,0` on a heterogeneous dual-GPU host. This makes the vision-isolation test depend on the machine running it.

Set `gpu_order: as_given` in that fixture so it tests the vision encoder's separate device selection with a fixed engine order. `test_card_order` already covers automatic ordering. Production behavior is unchanged.

Validation: the `GpuChoice` test class passes on the affected Windows dual-GPU host. The integrated branch also passes all 283 server, prompt-encoder and idle-status tests.
