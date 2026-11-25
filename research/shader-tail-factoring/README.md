# Factor common tails before shader compilation

Large generated shaders can repeat the same computation inside many switch arms. This PortBridge pass finds compatible straight-line tails and moves one shared body after the branch. The original arms still compute and choose their own inputs. A typed parameter column captures each different value across incoming edges, like a PHI node. The pass ships as a small Python component with HLSL and C emitters independent of the benchmark.

## Where the time went

PortBridge MCP surfaced an open mixed-sampler workload with repeatable compiler pressure. On its 2,048 sampling branches, DXC took 1.294 s median and 101.6 MiB of peak working set. Those branches contain different stores and a sampling operation, so they are a rejection control for this pure arithmetic pass. The public XCL compiler report motivated scaling both branch count and body size. It establishes a separate case of compiler pressure, with different inputs and without a measured link to our repeated-tail mechanism. [Xbox2Windows #801](https://github.com/R0Y00/Xbox2Windows/pull/801) · [Pinned control source](https://github.com/R0Y00/Xbox2Windows/blob/721dc1d97f02207ab4a6d74f8d3394f942b303c4/tools/dxc_compile_time.py) · [XCL #1269](https://github.com/xcl-dev/xcl/issues/1269)

In the largest repeat-shape case, one instrumented DXC run reported 96.5 ms in compiler passes before the rewrite and 5.0 ms after it. The reported baseline included 52.0 ms across instruction-combining passes and 17.0 ms in always-inline processing. This establishes repeated intermediate work in this construction. The ordinary timings below used fresh compiler processes without diagnostics. [Pass profile and raw compiler observations](compiler-results.json)

## Measured results

The arithmetic workload uses the published PCG RXS-M-XS hash with different initial input expressions in an independently generated switch. Its 8- and 32-way dispatch topology is synthetic. Separate families vary branch count, body length and the number of differing constants. A different final opcode in one arm is a rejection control. [GPU hash paper](https://jcgt.org/published/0009/03/02/) · [PCG reference paper](https://www.pcg-random.org/paper.html)

| Case | DXC -O3 wall, ms | DXC peak CPU working set, MiB | Final SPIR-V bytes after DXC -O3 and SPIRV-Tools -O | RTX D3D12 PSO creation, ms |
| --- | ---: | ---: | ---: | ---: |
| PCG hash, 8 modes | 18.84 → 17.38 | 18.55 → 18.17 | 3,584 → 2,184 | 1.704 → 1.524 |
| PCG hash, 32 modes | 25.69 → 19.50 | 19.58 → 18.59 | 10,512 → 4,312 | 2.923 → 1.700 |
| 16 arms × 16 arithmetic rounds | 51.81 → 19.78 | 23.35 → 18.60 | 28,468 → 4,468 | 5.693 → 1.764 |
| 64 arms × 16 arithmetic rounds | 164.96 → 22.92 | 37.99 → 18.90 | 108,484 → 7,684 | 17.601 → 2.330 |
| 16 arms × 64 arithmetic rounds | 161.07 → 27.02 | 37.55 → 19.61 | 106,884 → 10,884 | 16.764 → 2.714 |
| 16 arms, 17 varying parameters | 53.54 → 22.68 | 23.40 → 18.92 | 32,308 → 10,548 | 5.793 → 2.134 |

The shader CPU medians use eleven fresh compiler processes per arm, alternating the order. Each DXC stage emits binary only. The row with 64 arms used 3.22 ms for Python planning. Its compilation chain of DXC to SPIR-V followed by SPIRV-Tools took 315.13 → 42.10 ms. The CPU results include compiler startup and binary output. DXC output bytes used for the D3D12 replay matched the binary-only run exactly.

The physical D3D12 replay used an RTX 4070 Ti SUPER with driver 617.14 and nine fresh processes per arm. It supplies no caller pipeline-cache blob and keeps existing system and driver caches. Reported GPU utilization at the boundaries of the suite was 47% and 43%. A few first PSO timings were large. For 64 arms, the complete replay process including initialization, PSO creation, dispatch and readback took 227.7 → 212.4 ms median. That whole-process measurement starts after the DXIL file exists. The 32-mode PCG replay process was 213.6 → 211.1 ms. The observed PSO phase reductions have different effects on total process latency. [D3D12 observations and exact shader hashes](d3d12-results.json) · [Microsoft CreateComputePipelineState](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-createcomputepipelinestate)

Modern Clang -O3 already implements a comparable reduction on the C analogue of PCG. Both forms have 74 optimized SSA definitions for 32 modes. For the 64-arm arithmetic case Clang emitted 209 → 146 SSA definitions. The relevant comparison for shader output is the already-optimized DXC binary or DXC followed by SPIRV-Tools -O. An early pass can save the cost of constructing repeated IR even where a later optimizer partially merges it. [LLVM SimplifyCFG source](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Transforms/Utils/SimplifyCFG.cpp) · [SPIRV-Tools optimizer](https://github.com/KhronosGroup/SPIRV-Tools#optimizer)

## Correctness and scope

The original input is a structured switch with one local result per arm. Every instruction is a defined, pure unsigned 32-bit operation. Shifts use the low five input bits on every path. Earlier locals dominate their uses within the arm. External uses in a candidate slice are represented by their exact value at each incoming edge. Internal uses must refer to the same relative operation in every arm. Inducting from the first retained instruction then gives the same result on every reachable arm and input. The implementation counts one PHI and one incoming edge per arm as a size cost. It uses a monotone structural bound and examines up to 32 candidate cuts by default. The cost estimates code change, and measured compilation determines its impact.

The prototype covers one terminal pure region at a time. Its rejection boundary includes texture or memory effects, barriers, subgroup operations, floating-point exceptions, arbitrary graph rewrites and conflicting internal dependency shapes. The positive examples establish a substantial gain for repeated generated switch regions. Testing a receiving compiler requires measuring the frequency and size of those shapes in an independently pinned open emitter without modifying its surrounding effects.

To embed the pass, construct a validated `Region`, call `factor(region)`, and use the returned plan with that same region in `evaluate` or `emit`. A missing plan keeps the original region. The lower-level candidate builder assumes that the structural scan has already admitted the selected suffix.

All seven component tests passed. Clang -O3 native C libraries agreed with the separate model on 1,024 tuples for each of the seven paired forms. D3D12 validated 138,240 readback words on the RTX and 25,600 more on WARP. Both optimized and pre-SPIRV-Tools SPIR-V binaries passed structural validation. The dispatch reads include a queue fence and one small readback and provide a correctness check. Windows initialization and graphics-driver caches are relevant to broader startup measurements. [Microsoft root descriptors](https://learn.microsoft.com/en-us/windows/win32/direct3d12/using-descriptors-directly-in-the-root-signature)

## Reproduce

Use Python 3.11 or newer. The recorded build used DXC 1.9.2609.5, Clang 23.1.6 and SPIRV-Tools v2026.5 at `g340b4c41`. The Khronos [pinned Windows build archive](https://storage.googleapis.com/spirv-tools/artifacts/prod/graphics_shader_compiler/spirv_tools/windows-vs2022-amd64-release/continuous/304/20261124-071623/install.zip) had SHA-256 `07f1466330427d3e0780b33fc337e3ccfe931d6c72f6df29dfa070fed404595e`. Run the following in this directory with the executables on PATH.

```powershell
python -B -m unittest discover -s . -v
python -B benchmark.py --dxc dxc.exe --spirv-opt spirv-opt.exe --spirv-val spirv-val.exe --clang clang.exe --rounds 11 --directory out/cpu --output out/cpu.json
python -B llvm_baseline.py --clang clang.exe --generated out/cpu --output out/clang.json
clang++ -std=c++20 -O3 -static -Wall -Wextra -Wconversion -Werror warp_replay.cpp -ld3d12 -ldxgi -o d3d12_replay.exe
python -B benchmark.py --dxc dxc.exe --spirv-opt spirv-opt.exe --spirv-val spirv-val.exe --clang clang.exe --replay (Resolve-Path d3d12_replay.exe) --adapter warp --rounds 5 --emit-listings --cases pcg-32 pure-64x16 heterogeneous-16x16 --directory out/warp --output out/warp.json
```

Use `--adapter rtx4070ti-super --rounds 9` and omit `--cases` to repeat all physical observations on the exact named adapter. The two D3D12 runs also use `--emit-listings` to reproduce the earlier compile commands. Their reported PSO timings come from a separate process that consumes the binary only.

For the [open negative-control observations](xbox2windows-control-results.json), save the [pinned Xbox2Windows script](https://raw.githubusercontent.com/R0Y00/Xbox2Windows/721dc1d97f02207ab4a6d74f8d3394f942b303c4/tools/dxc_compile_time.py) locally as `dxc_compile_time.py`. Its SHA-256 is `09327aa31cd1c5eef51e48384e81c2f594978e1811e27f8ac0176a1442c9382e`. The command runs the source as provided by Xbox2Windows.

```powershell
python -I dxc_compile_time.py --dxc (Get-Command dxc.exe).Source --variants control,samples_256,branches_256,samplebranch_512,samplebranch_2048 --repeat 3 --timeout 20 --ftime-report --out out/public-control.json --work-dir out/public-control
```

The analysis and prototype are MIT. The external control script remains licensed by its upstream project. The measured records contain tool versions, generated hashes and timings. The benchmark regenerates all locally used shaders from source.
