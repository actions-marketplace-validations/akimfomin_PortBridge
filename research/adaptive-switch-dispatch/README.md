# Adaptive two-level shader dispatch

A single shader switch with thousands of independent targets can leave thousands of inputs at one SSA join. Splitting the switch into smaller groups redistributes that work. Pipodi’s XCL #2025 used fixed groups on compact case IDs and reported 168 to 36 seconds on one cold 2,516-case NVIDIA driver build. Other configurations and follow-up grouping methods had mixed results. The PortBridge experiment addresses shaders whose 32-bit labels are already assigned and may be sparse, and measures a separate CPU compilation pipeline. [Existing XCL work](https://github.com/xcl-dev/xcl/pull/2025)

## Implementation

[`dispatch.py`](dispatch.py) evaluates contiguous windows in the selector. It scores each split by the sum of squared outgoing edge counts across the outer and inner switches, counting default edges. The score prioritizes splitting very wide joins while charging for the number of buckets. The selector itself is kept as a full unsigned 32-bit value inside each bucket. An inner miss and an outer miss both run the original default. Signed decimal spellings from the int32 range use the corresponding bit pattern, and duplicate bit patterns are rejected.

For an input with a matching label, the selector and that label necessarily project to the same bucket, where exact 32-bit equality selects the original arm. An input with no matching label cannot enter an arm even when its projection collides with an existing bucket. The emitter accepts independent statements with no cross-case fallthrough and assumes a stable local uint selector. It does no CFG rewriting and adds no data buffers. [DXC lowering and Vulkan bindings](https://github.com/microsoft/DirectXShaderCompiler/blob/01b62ad47/docs/SPIR-V.rst#switch-statement) · [SPIR-V OpSwitch semantics](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpSwitch)

Only use this emitter with convergence-insensitive arm and default bodies. The lowered switch can run copies of the default at distinct control-flow sites. Subgroup operations, quad derivatives, and other collective behavior would require a separate equivalence argument.

The experimental default keeps switches below 1,024 cases flat and requires a fourfold reduction in the structural score for larger switches. The floor reflects the exploratory 512-case results. The score measures switch geometry. Driver compilation and the number of resulting basic blocks require separate measurements.

## Results

| Synthetic workload | Cases | Flat | Fixed middle bits | Fixed high bits | Default policy | Radix without size gate | 32-case comparison tree | Metadata table |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Small spread | 24 | 64 ms | 78 ms | 76 ms | 76 ms | 66 ms | 77 ms | 59 ms |
| Dense across signed zero | 512 | 433 ms | 374 ms | 404 ms | 445 ms | 418 ms | 394 ms | 72 ms |
| Strided, identical low bits | 512 | 446 ms | 452 ms | 396 ms | 450 ms | 423 ms | 394 ms | 72 ms |
| Sparse across uint32 | 2,048 | 3,247 ms | 3,121 ms | 2,000 ms | 1,920 ms | 1,799 ms | 1,835 ms | 73 ms |

The large sparse workload’s default-policy median fell 40.9% relative to flat. After both compilers, maximum switch edges and maximum PHI inputs fell from 2,049 to 129. Optimized SPIR-V grew from 347,116 to 362,516 bytes. The 32-case comparison tree reached 33 edges and 360,984 bytes, with a comparable total compile time. The two radix columns independently timed the same generated layout for this workload and differ by 121 ms, limiting what this run establishes about small gaps. The default policy emitted the same flat source below 1,024 cases, so those timing differences also illustrate noise.

The CPU timings cover HLSL generation (including plan search and temporary file write), DXC `-O3 -spirv` targeting Vulkan 1.2, and `spirv-opt -O`. Each workload uses five interleaved rounds with a shuffled variant order and fresh compiler processes. [Raw timings and CFG counts](benchmark-results.json)

The 32-case comparison tree routes full keys by sorted upper bounds. The two fixed radix variants use the same case bodies as the adaptive version and only change projection. The table baseline substitutes binary search over an added sorted-key resource and four shared arithmetic bodies. It compiles much faster on this workload because its cases can be described as data. The table changes resource binding and runtime reads, and its GPU cost was not measured.

The native replay compiles the emitted case bodies as C++ with Clang, then checks all case labels, neighboring misses and random inputs against a separate uint32 reference. All 86,576 comparisons across seven layouts passed. The generated Vulkan SPIR-V modules pass the Khronos validator before and after the optimizer. Those checks cover the stated transformations and module structure. GPU execution, driver pipeline creation, peak memory and external shader workloads remain unmeasured. [Native replay counts](native-results.json) · [SPIRV-Tools](https://github.com/KhronosGroup/SPIRV-Tools)

PortBridge preflight found the exact XCL thread and also surfaced the separate Five Star work on carrying live registers between dispatch cases. These are distinct ways to reduce the size of large dispatch joins. [Five Star code](https://github.com/ThatRecompDev/five-star-recomp/commit/1a8083a405b3d4cb85c1c83709a8c1d8ce4a4b7c)

## Reproduce

From this folder, use Python 3.10 or newer. The benchmark used DXC 1.9.2609.5, SPIRV-Tools v2026.5 and Clang 23.1.6 on Windows.

```powershell
python -B -m unittest discover -s . -v
python -B replay_native.py --clang clang++ --output native-results-local.json
python -B benchmark.py --dxc dxc --spirv-opt spirv-opt --spirv-val spirv-val --output benchmark-results-local.json
```

Pass absolute paths for tools that are outside PATH. The fixture sources are generated locally and use only synthetic uint32 data. The next adoption criterion is a pinned open workload with sparse literal tags and distinct case bodies, followed by matching output readbacks and paired cold pipeline measurements against both the best fixed layout and the table form where applicable.

The source and generated fixtures use the repository’s [MIT license](../../LICENSE).
