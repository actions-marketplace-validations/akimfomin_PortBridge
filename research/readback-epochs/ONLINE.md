# Online adaptive readback

The online planner sees one ordered batch of known writes and observations at a time. Exact asynchronous reads, always-retained observations, and adaptive reads share a single Vulkan queue, three staging slots of the same declared capacity, and the same CPU consumer. The historical `guarded` mode remains available as an offline experiment. Its whole-trace decision and future packing are outside the online comparison.

## Decisions and completion

All ranges must refer to the same stable, canonical allocation. The policy retains one bounded packed observation shape. It repeats exact reads while a new shape is uncertain, and may populate a mirror when a repeated shape has little current overlap with writes. It estimates the relative cost of missing pages, copy regions and the host mirror update. Dense writes, fragmentation or insufficient savings keep exact reads. The executable also requires at least 64 KiB in potential savings per request. This conservative threshold is a configurable quantity in the planner, not a hardware-calibrated universal limit. When the declared request capacity cannot reach that threshold, the executable bypasses the adaptive planner.

Writes invalidate promises for affected mirror pages. Exact reads do not make those pages valid. A retained copy creates a promise for later recording only. It reaches the CPU mirror after a transfer-to-host barrier and fence, at FIFO retirement. If the retained shape changes, the runner drains outstanding frames against the previous mirror before the new shape can populate it. Validation, decisions, command recording, submissions, waits, cold mirror growth, mirror copies and CPU consumption all enter wall time. Staging allocation and source zero-fill are outside it. Readback errors require abandoning state and rebuilding it.

The policy receives no future writes, reads or precomputed deltas. Its staging capacities are declared in the input contract and are identical across arms. Cache data grows only at a selected seed. Reported mirror bytes exclude interval metadata and Vulkan or allocator bookkeeping. A retained mirror can increase actual memory use relative to exact reads. No old snapshot may be exposed early, even when no new transfer is needed. The replay retains all queue submissions in all modes.

[Implementation](online_readback.hpp) · [Vulkan synchronization](https://docs.vulkan.org/guide/latest/synchronization_examples.html#cpu-read-back-of-data-written-by-a-compute-shader)

## Workload and limits

- **OpenLyceum HeatTransfer.** The original update and read methods were run against a mock WebGPU device. The resulting traces cover the full overwritten 128² and 2048² fields and different readback completion cadences. No stale or reused value is assumed.
- **SNOWFLOW.** The original CPU controller tools captured reads along two scripted routes on generated heights. For each route the replay compares both exact four-byte words and the same requests rounded to 4 KiB. On the primary route, this rounding raises the exact requested 31,104 bytes to 9,863,168 bytes. Adaptive performance on artificially coarser requests cannot establish a benefit on the exact route.
- **SNOWFLOW stock bake.** The one-shot, 128 MiB initial transfer records the stock call shape. The original then downsamples, computes height limits and reads from CPU memory. Our deferred readback replay is counterfactual. It excludes those initial reductions and assumes each current callback's requested addresses are already known. It does not measure either original application's full runtime.
- **Water texture control.** A 256² height/displacement-sized synthetic buffer with a local crop and full writes models one possible case for VIctory Fork #999. The dimensions come from the public code. The write cadence and crop are chosen controls.
- **Switch control.** A 16 MiB field switches between local writes, full updates and a shifted observation shape. This is a generated sensitivity case, not an engine trace.

Each physical replay uses PortBridge's integer Vulkan producer. Every word in the exact requested union contributes to a position-weighted 64-bit validation checksum. The CPU tests independently check complete snapshot vectors rather than checksums. Page rounding, command/callback geometry and reuse differ among the fixtures. The runner reports time through host consumption, without inferring rendered frame rates or claiming direct application measurements. [Source pins, licenses and capture tools](source-traces/PROVENANCE.md) · [VIctory Fork #999](https://github.com/fxceless/victory-fork/pull/999)

Every online fixture has a zero-length offline delta list. A prefix-invariance test verifies that changing later events cannot affect earlier choices. CPU tests cover mixed exact and retained slots, invalidation, rebinds, a cache-cap limit and 8,000 FIFO snapshots. Unknown CPU access, allocation remapping, unresolved aliases, multiple queues and synchronization not represented in the trace require an existing conservative path. An engine adapter must prove allocation identity and actual observation bounds separately.

## Measured result and disposition

RTX 4070 Ti SUPER, driver 617.14, Vulkan 1.4.351. The final matrix has 360 trials and 43,524 validated frame results across ten traces. The omitted-producer negative control was rejected at frame zero. Samples between blocks showed 52–73% device activity. Exact-equivalent routes varied substantially in the measurements. [Raw timings](evidence-online/hardware.csv) · [Paired summary](evidence-online/summary.json) · [Workloads and bounds](evidence-online/workloads.json) · [Environment](evidence-online/environment.json) · [Negative control](evidence-online/negative.log)

| Case | Exact path | Adaptive route or result |
| --- | --- | --- |
| HeatTransfer full-field controls | The large prompt-completion case transferred 192 MiB in 48 steps | Same copies and no allocated mirror. Always-retain added 45.3% median time on that control without saving transfers. |
| SNOWFLOW exact grounding | Primary/holdout requested 31,104 / 31,056 bytes across 240 frames | Same copies and no allocated mirror after the byte gate. In an earlier ungated pilot exact-word savings failed to produce a consistent latency gain. |
| SNOWFLOW grounding rounded up to 4 KiB | Primary requested 9,863,168 bytes after rounding | All requests remained exact under the byte gate. They model a different contract than the original scalar loads. |
| SNOWFLOW one-shot stock and typed-water full-write controls | Whole bake and exact crop respectively | Same transfers and no allocated mirror under the byte gate. |
| Switch-16 synthetic phase control | Median 27.40 ms per 56 frames, 224 MiB copied, 12 MiB staging | 22.56 ms, 77.43 MiB copied, and 4 MiB extra mirror. Paired time fell 16.9% over six faster blocks. The result includes 3 seeds, 39 retained frames, and one rebind with two extra slot drains. |

The measurements support a conditional technique for repeated larger regions with localized changes. They do not establish system-wide gains for the observed application contracts. In particular, original SNOWFLOW already keeps its field in CPU memory after the one-time initialization. Replacing that flow with recurring transfers remains unsupported. Immediate production integration is deferred until a real consumer supplies known expensive observation ranges and evidence of meaningful reuse.

## Reproduction

Build the same Vulkan replay and shader described in the [historical reproduction guide](README.md#reproduction). The online generator uses Python and NumPy for an independent vectorized checksum oracle. Already captured source events are included in compressed form. From this directory:

```sh
c++ -std=c++20 -O2 test_online_readback.cpp -o scratch/test-online
scratch/test-online
python -B make_online_traces.py scratch/online-traces
python -B run_online.py scratch/readback scratch/terrain.spv scratch/online-traces scratch/online-results --device "device name"
```

The test cycles through all six orderings of the modes. Each separate process warms up then records two repeats. Comparison uses the median of each block's two repeats, then pairs those medians. The optional `--nvidia-telemetry` records activity between blocks. It does not control background workloads.
