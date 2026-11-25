# Transient Slot Cover

Two GPU queues can overlap. A single topological ordering of their passes can make two transient resources appear disjoint even when another legal schedule overlaps them. Disallowing cross-queue reuse avoids that problem but leaves already-ordered opportunities unused. Granite's open implementation, for example, confines its render-target aliases to one queue. PortBridge preflight found a corresponding cross-queue verification need in FrameLab. [Granite's allocator](https://github.com/Themaister/Granite/blob/69f450c62dc3780680b936539a931b5d03e436fb/renderer/render_graph.cpp) · [FrameLab #2](https://github.com/5headsmartbtw/leonida-framelab/issues/2)

[slot_cover.py](slot_cover.py) computes the fewest whole slots for exact allocation classes. The caller supplies all access passes and dependencies that guarantee a pass has completed before the next starts. The last access frontier of the old resource must precede every member of the first access frontier of the new one. This condition holds for every schedule consistent with the dependencies. The solver adds no execution-order edges. It uses maximum bipartite matching, a standard way to find a minimum path cover in a DAG. PortBridge's component builds the safe resource edges and returns the required handoff points alongside the allocation plan.

An allocation class represents a caller-certified common memory type, extent, alignment and alias compatibility. A resource may follow another only when its caller certifies that it does not need the prior contents. This must hold at every relevant first access in every permitted schedule. A write on only one branch is insufficient. Send only transient resources with complete access sets. Data that must survive the frame or an external consumer requires its accesses to be represented or kept outside this plan.

The caller still owns memory visibility, layout transitions, initialization, queue ownership and API aliasing barriers. In Vulkan, execution ordering alone does not make writes visible. In particular, slot counts are payload extents within this fixed whole-slot model. They exclude driver allocation overhead, variable-size packing, and the cost of recording handoffs. [Vulkan synchronization rules](https://docs.vulkan.org/spec/latest/chapters/synchronization.html) · [Vulkan memory allocation](https://docs.vulkan.org/spec/latest/chapters/memory.html) · [D3D12 aliasing barriers](https://learn.microsoft.com/en-us/windows/win32/direct3d12/using-resource-barriers-to-synchronize-resource-states-in-direct3d-12)

## Comparison

Compare with greedy first-fit using the same happens-before checks and with first-fit restricted to resources on one queue. The Granite projection models the documented bloom/exposure pass relationships with chosen extents and dependencies. Queue preference itself selects the optimum in the crafted crossing case. The varied cases use independent fixed seeds and an explicit simulated dependency graph.

| Workload | Same-queue first-fit | Safe cross-queue first-fit | Slot cover |
| --- | ---: | ---: | ---: |
| Serial chain, 96 resources | 128 KiB | 128 KiB | 128 KiB |
| Granite bloom projection, 5 resources | 6,208 KiB | 6,208 KiB | 6,208 KiB |
| Crafted crossing, 64 resources | 2,048 KiB | 3,072 KiB | 2,048 KiB |
| 64 varied synthetic graphs, sum | — | 84,928 KiB | 83,008 KiB |

Slot Cover improved 23 of 64 varied cases and used 2.26% less modeled slot storage in aggregate. In the serial chain, one local run took about 2.1 ms with matching and 0.34 ms with safe first-fit. Pooling gains do not imply a frame-time gain. The matcher uses worst-case cubic time and quadratic adjacency space per class. The two measured controls with existing queue-first options did not show a storage gain. Priority remains behind the compiler work until an authorized engine trace exposes repeatable savings over the engine's allocator.

The committed small-graph suite enumerates legal pass schedules and all slot partitions for 400 cases. An independent reviewer also checked optimal byte counts against subset dynamic programming on 3,000 DAGs, all 655 emitted handoff frontiers, and matching on 3,000 generic bipartite graphs. [Granite renderer topology](https://github.com/Themaister/Granite/blob/69f450c62dc3780680b936539a931b5d03e436fb/README.md#render-graph)

```sh
python -B -m unittest discover -s research/transient-slot-cover -v
python -B research/transient-slot-cover/compare.py
```
