# Timing the Continued subgroup transport rewrites

Two open Continued fixtures compare the original lowering, the default PortBridge rewrite, and the full-subgroup specialization. All modules were generated from Continued `1bedab24c39d0b3ae325f6f0f6c43e47bbb6430e` and run through the same SPIR-V Tools `-O`. The 64-invocation `bpermute` shader is eligible for full specialization. The 40-invocation `partial` shader retains its guards. Its default and full variants are byte-identical, so they also measure timing drift between identical binaries. [Synthesis and fixture provenance](../SYNTHESIS.md)

The GPU measurement uses a dedicated command buffer with timestamps around either one dispatch or 32 serial dispatches. The latter writes one shared output buffer and contains a compute memory barrier before each dispatch. The run checks that the buffer is unchanged from the untimed dispatch and then matches all 256 output words to the known fixture. Each fixture and batch size has nine paired rounds with rotated execution order. Each arm contains a fresh pipeline process, eight warm-ups, and 24 samples. Submit-to-idle measurements include CPU and driver latency. No pipeline creation, readback transfer or application frame is included in those intervals. Timestamp deltas use the queue family's valid bits and the physical device's timestamp period. [Timestamp specification](https://docs.vulkan.org/spec/latest/chapters/queries.html#queries-timestamps) · [Khronos timing sample](https://docs.vulkan.org/samples/latest/samples/api/timestamp_queries/README.html)

The run used an RTX 4070 Ti SUPER and NVIDIA driver 617.14 with fixed Wave32. Sampled background GPU utilization ranged from 47% to 60%, at a reported 2,805 MHz SM clock. The threshold for pursuing a throughput rollout was a paired device-time improvement of at least 5% and 100 ns per dispatch, with at least seven of nine rounds faster and matched fallback output.

| Fixture | Batch size | Original median ns per dispatch | Default median | Full median | Paired full minus original |
| --- | ---: | ---: | ---: | ---: | ---: |
| bpermute | 1 | 1,808.0 | 1,824.0 | 1,792.0 | −48.0 ns in 5 of 9 faster rounds |
| bpermute | 32 | 1,039.0 | 1,036.5 | 1,006.0 | −33.0 ns in 9 of 9 faster rounds |
| partial | 1 | 2,208.0 | 2,272.0 | 2,208.0 | 0.0 ns |
| partial | 32 | 1,520.5 | 1,519.0 | 1,520.0 | 0.0 ns |

All 2,592 measured samples were taken in processes with identical checked output. The single-dispatch series did not consistently improve. The full-subgroup result in the batch of 32 was about 3.2% smaller on these fixtures and missed the practical threshold. Host-side data varied even when two binaries were identical. Keep the specialization available for guarded experiments. There is no timing evidence here for application throughput or physical Wave64.

## Reproduce

Use a disposable, clean Continued checkout at the exact revision above. Apply [continued-timestamps.patch](continued-timestamps.patch) and compile its `vk_compute_test` target or the standalone source with C++20 and Vulkan headers. The Windows run used Clang 23.1.6 and Vulkan-Headers `6802bb4733b63ed5efd3adb308a6c885ef180ea1`. Generate the modules and trusted output using the regular replay on a second clean checkout, then point the comparison at its output directory. Use the same adapter and reported width in both steps.

```sh
python -B research/subgroup-validator/replay_continued_synthesis.py --checkout /path/to/clean-continued --spirv-tools /path/to/tools/bin --output /path/to/modules --vulkan-runner /path/to/vk_compute_test --device "RTX 4070 Ti SUPER" --subgroup-width 32
python -B research/subgroup-validator/timing/compare.py --runner /path/to/vk_compute_timed --shaders /path/to/modules --device "RTX 4070 Ti SUPER" --width 32 --output /path/to/results.json
```

[Machine-readable samples](timing-rtx-raw.json.gz) include separate device and submit-to-idle samples, round order, full-output hashes and timing controls. The patch to the upstream runner follows [Continued's GPLv3 license](COPYING). The standalone Python comparison script is MIT.
