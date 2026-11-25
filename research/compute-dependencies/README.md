# Compute dependencies

This CPU-only analysis takes a fixed sequence of compute and transfer operations on one queue. Each operation declares its complete read and write footprints as half-open byte ranges on canonical buffer identities. It finds overlapping RAW, WAR and WAW hazards and compares two ways to cover the same dependencies.

- `Schedule.baseline` is a minimum-count schedule of ordinary barrier cuts for the fixed order and unit cost per cut.
- `Schedule.ordinary` and `Schedule.events` split that same coverage between ordinary cuts and optional early signals with late waits. One event replaces one whole cut group. `event_budget` bounds the total number of events allocated to the trace, without event reuse.

For a hazard from operation `i` to operation `j`, any cut before an operation with index in `[i+1, j]` covers it. The algorithm sorts those intervals by right endpoint. When an interval is uncovered, it chooses the right endpoint. Every next triggering interval begins after the previous cut, so the triggering intervals are disjoint. Any schedule must use at least one cut per triggering interval. The algorithm achieves that bound. It then assigns each hazard to its latest covering cut, preserving the same minimum number of cuts and keeping dependencies out of earlier groups when a later group can handle them.

An event signals immediately after the latest producer in its group and waits at the original cut. The selector gives the available events to groups with the most operations of the same source stages between the signal and wait. This counts possible overlap. It does not measure hardware latency, GPU overlap, or application throughput. Multiple windows can count the same intervening operation. The selector does not reorder operations, optimize measured costs, or account for interactions between event windows.

## Reproduction

```sh
python -B -m unittest discover -s research/compute-dependencies -v
python -B research/compute-dependencies/halide_trace.py
```

The fixed-order cut tests exhaust all 1,098 sets of forward hazard intervals on two to five operations. The model also checks half-open overlap, all three hazard kinds, event budgets, and conservative rejection of unsupported operations. The Halide-shaped fixture models two independent masked-relaxation streams with ping-pong field buffers and real transfer checkpoints. The transfer reads the latest computed field and writes independent storage, and the next overwrite of its source must wait for the transfer to read it. This is an access trace inspired by a public benchmark. It does not build or run Halide. [Pinned Halide benchmark](https://github.com/halide/Halide/blob/1e784ed82ffb31a3927da12dbf3cd08f5f81f522/test/performance/gpu_dispatch_overhead.cpp#L39-L95)

| Trace | Operations | Hazards | Minimum ordinary cuts | Selected split events |
| --- | ---: | ---: | ---: | ---: |
| Two interleaved streams plus checkpoints | 32 | 264 | 16 | 4 |
| Single dependent stream | 12 | 102 | 11 | 0 |

Each of the four selected mixed-trace windows contains one intervening compute operation in the other stream. A strong future GPU baseline should use batched dispatches with compute and transfer scopes and compare the minimum ordinary cuts above. Halide's draft batches up to 32 commands and places a compute/transfer barrier before each. The cut count of a strictly dependent ping-pong chain is unchanged. [Pinned Halide baseline](https://github.com/halide/Halide/blob/1e784ed82ffb31a3927da12dbf3cd08f5f81f522/src/runtime/vulkan_resources.h#L605-L683)

## API boundary

Call `analyze(operations, event_budget=4)` from `compute_schedule.py`. The caller must canonicalize aliases, validate the buffer bounds and know every access. Unknown accesses, aliasing through undeclared identities, lifetime changes, graphics, images, host visibility and queue ownership are outside this model. Feed opaque operations to a conservative existing path instead of omitting them. Pairwise hazard discovery is quadratic in the trace length.

The analysis does not emit GPU commands. A Vulkan lowering must use concrete stage and access scopes that cover each group's hazards. An ordinary barrier waits on its source stages across the submitted prefix. Narrowing a buffer range limits the affected memory scope. For a split event, Vulkan 1.3 or enabled synchronization2 is needed. The signal and wait must be on the same queue and have matching dependency descriptions. Events must not be reset or reused while a prior signal or wait can still be active. Use a separate completion and visibility path for host reads. [Vulkan signal](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdSetEvent2.html) · [Vulkan wait](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdWaitEvents2.html) · [Synchronization examples](https://docs.vulkan.org/guide/latest/synchronization_examples.html)
