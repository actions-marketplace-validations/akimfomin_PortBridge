# Observation-scoped GPU readbacks

A GPU may write a buffer several times before a CPU observer uses it. Copying the entire allocation, or even the exact requested ranges on every observation, can repeatedly move bytes already present in the host mirror. The planner tracks which bytes of each canonical backing have changed. At a CPU observation it returns only the dirty part of the combined requested ranges. Bytes known to be current stay in the mirror.

## Where the problem matters

A VIctory Fork contributor measured copy-back scopes of 32.9–97.6 ms in six 272–701 ms frames on a laptop RTX 4060. The scopes include waiting. Other phases also change between branches, so that report gives no isolated estimate of the effect of reducing bytes. XCL #1993 instead removes synchronous waiting in one queue path, and its author reported initial peak memory rising from 15.1 to 17.0 GB while async buffers accumulated. KLBF Lab beta has an explicit CPU consumer of a 256×256 GPU height map, and the published implementation copies entire matching subresources. Its actual observed byte ranges and frequency were unavailable. [VIctory Fork report](https://github.com/fxceless/victory-fork/issues/1003) · [XCL memory report](https://github.com/xcl-dev/xcl/pull/1993#issuecomment-7167472136) · [KLBF beta readback](https://github.com/PastiiJay/klbf-lab/blob/82838a15f5d3fa67cb5919c84d9e379a9ac72481/crates/victory-gpu/src/texback.rs#L1-L20)

Batching, asynchronous staging and exact-range readback are established approaches. The strongest comparison in this replay uses exact contiguous ranges from the same requests, a bounded ring of three buffers, mapped host-cached memory, one batched copy command and one fence per frame. This approximates scoped asynchronous access such as Godot's `buffer_get_data_async`. It does not run Godot or XCL. The planner adds reuse across observations and explicit alias handling. [Godot exact-range readback](https://docs.godotengine.org/en/stable/classes/class_renderingdevice.html#class-renderingdevice-method-buffer-get-data-async) · [victory-perf readback architecture](https://github.com/vitutu1/victory-perf/blob/52a60947ff93998675d3c5171ba1d79b312a0761/README.md#original-gpu--cpu-performance-work)

## Contract and implementation

[The interval planner](epoch_plan.py) accepts writes and observations in visibility order. Views resolve to a canonical identity and byte range, so overlapping views share one dirty set. The host mirror starts current. A write marks a range dirty. Each batched observation first validates and unions its ranges, then intersects and removes the observed dirty bytes in one sweep. An opaque observer flushes all dirty data in its declared canonical backing set. If a target has unknown aliases or untracked CPU access, the adapter must keep its existing visibility path. Observations grouped in one call must see the same write epoch.

The adapter must capture the result before a subsequent write can overwrite it, complete the copies and CPU mirror updates in the promised order, and deliver the observation only then. On failure it must discard or reestablish the plan state. The planner does not model CPU writes, unknown backings, images with tiling rules, multiple queue ownership or page faults. A pending transfer alone is also insufficient for exposing CPU memory. [Vulkan synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html)

The software tests compare against a separate byte-by-byte eager mirror on 12,000 events and cover alias overlap, superseded writes, unknown backings and the conservative observation path. The Vulkan replay uses one ordered queue and drains its three slots in order. It validates three independently generated words per observed page and frame. Each changed region in the replay receives distinct deterministic integer data from the GPU. CPU copies into the private mirror and the sample check are included in end-to-end timings.

## Measured result

Physical RTX 4070 Ti SUPER, NVIDIA 617.14, Vulkan 1.4.351. Every one of the 6,144 measured frames matched the independent CPU sample hash. The deliberately removed first delta failed on frame zero. Four balanced blocks compare batches of 48 frames. GPU utilization samples between blocks ranged from 45% to 100%. Route-equivalent controls show significant timing noise. [Raw paired trials](evidence/hardware.csv) · [Expected trace metrics](evidence/workloads.json) · [Environment](evidence/environment.json) · [Negative control](evidence/negative.log)

| Trace | Exact ranges, median ms | Epochs, median ms | Paired epoch change with separate Python planning charge | Bytes avoided vs exact | Staging plus mirror, exact → epochs |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8 MiB, stable observations | 12.17 | 5.53 | −46.8% | 91.1% | 6.00 → 4.92 MiB |
| 32 MiB, stable observations | 43.56 | 12.47 | −69.4% | 83.3% | 24.00 → 21.33 MiB |
| 32 MiB, rolling probes | 22.99 | 12.78 | −21.4% | 80.4% | 12.00 → 12.62 MiB |
| 16 MiB, moving windows | 11.46 | 9.66 | −13.9% | 84.0% | 6.00 → 7.51 MiB |
| 16 MiB, mostly dirty | 24.26 | 25.33 | +4.6% | 12.2% | 12.00 → 15.00 MiB |
| 32 MiB, global writes | 50.53 | 58.46 | +16.2% | 0% | 24.00 → 32.00 MiB |
| 32 MiB, opaque full read | 180.06 | 240.61 | +29.3% | 0% | 96.00 → 128.00 MiB |
| 256², global writes | 1.20 | 3.64 | +198.6% | 0% | 0.19 → 0.25 MiB |

Paired changes use medians of block-wise relative changes, so they can differ from ratios of displayed medians. The stable 32 MiB trace is the strongest result. Epochs won every block by 68.6–71.4% before the separate planning charge, and the independently replayed guarded route won all four blocks. Rolling probes also won all four raw pairs while consuming more host capacity. The moving-window holdout and the guarded small trace varied across blocks. The no-savings controls pick exact ranges. Large variation even between route-equivalent 256² controls limits the interpretation of small timings. [Paired detail and memory](evidence/summary.json)

A real integration still needs the actual write and observation intervals, a proven fallback for unknown access, and an independent physical run. No engine wall-time, driver stall reduction or process-wide memory change was measured. Production software already explores async staging, generation tracking and range-based ownership. This result isolates the value and cost of retaining already observed bytes in a separate portable component.

The [online follow-up](ONLINE.md) uses current-event decisions and whole-observation validation. Exact-word source-shaped controls show why the fixed-trace gain cannot be generalized to engine performance. The offline measurements above remain reproducible.

## Reproduction

Python uses the standard library. The physical runner requires a Vulkan 1.1 compute device, suitable device-local storage, and coherent host-visible cached staging memory. The replay uses an ordered input of 4 KiB pages. The planner itself accepts byte intervals. Each of the three staging slots reserves its largest packed transfer over the known trace. The epoch arm also reserves a packed mirror of the union of observed pages. Reported host capacity counts actual Vulkan staging allocation sizes plus mirror payload bytes. It excludes interval metadata, driver overhead, and process RSS.

From this directory on a system with installed Vulkan headers and loader:

```sh
python -B -m unittest discover -s . -v
python -B make_traces.py scratch/traces
glslangValidator -V --target-env vulkan1.1 terrain.comp -o scratch/terrain.spv
spirv-val --target-env vulkan1.1 scratch/terrain.spv
c++ -std=c++20 -O2 replay_vulkan.cpp -lvulkan -o scratch/readback
scratch/readback scratch/terrain.spv scratch/traces/stable-32.tsv ranges 6 "device name"
scratch/readback scratch/terrain.spv scratch/traces/stable-32.tsv epochs 6 "device name"
```

For LLVM-MinGW on Windows, generate the loader import library from the Vulkan calls in the single replay source, as described in the [Windows Vulkan toolchain example](../mipmap-contract/benchmark/README.md#reproduce). All variants accept the same traces. Mode `full` mirrors all storage each frame. Mode `ranges` copies the requested union. Mode `epochs` uses planner-produced deltas and the host mirror. Mode `guarded` selects epochs only when the known trace saves at least one MiB and its deltas use at most half the exact requested bytes. It selects exact ranges otherwise. This is an offline selection rule. The runner precomputes packing and warms up once before returning timed repeats.

The paired matrix uses four balanced mode orders and one measured repeat per arm and block.

```sh
python -B run_matrix.py scratch/readback scratch/terrain.spv scratch/traces scratch/final --device "device name"
python -B summarize.py scratch/traces/workloads.json scratch/final/hardware.csv
```

The runner uses the same compute commands, queue, slot count and observer on every arm. Full loop time covers recording, submissions, device computation, transfers, ordered fences and CPU reads. The epoch mirror's CPU copies are included. Setup, offline trace packing, and the Python planner are outside that interval. A second comparison also adds the separately measured planner time. The computed terrain data and read locations are generated. The replay tests the GPU-to-CPU chain without claiming performance for a rendered application.
