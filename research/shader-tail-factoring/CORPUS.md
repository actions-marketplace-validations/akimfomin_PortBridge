# Open-shader applicability census

The existing Shader Tail Factoring pass handles a switch whose distinct arms end in a common unsigned 32-bit arithmetic region. The scanner found **0 eligible regions across 373 validated open observations**. Keep the component for generators known to emit the pattern. Its sizeable synthetic gains give little reason to add it to a general shader pipeline without direct evidence from that generator.

## Inputs and measurements

- **MiniEngine.** Every HLSL `FxCompile` declaration in Microsoft's pinned Core project. The profile uses its desktop Shader Model 6.2 and HLSL 2021 settings. The census reuses the application sources and targets Vulkan SPIR-V to inspect a common intermediate representation. [Core project](https://github.com/microsoft/DirectX-Graphics-Samples/blob/68a2b1e97f71642924e74c7757ca21756ad221b5/MiniEngine/Core/Core.vcxproj) · [Desktop settings](https://github.com/microsoft/DirectX-Graphics-Samples/blob/68a2b1e97f71642924e74c7757ca21756ad221b5/MiniEngine/PropertySheets/Desktop.props) · [MIT license](https://github.com/microsoft/DirectX-Graphics-Samples/blob/68a2b1e97f71642924e74c7757ca21756ad221b5/LICENSE)
- **AMD FidelityFX FSR 2.2.1.** Eight full-precision HLSL passes and two combinations of the six build switches per pass. Both combinations use the other documented default definitions. The census samples the permutation space and does not model the frequency of settings on an installed system. [Core flags](https://github.com/GPUOpen-Effects/FidelityFX-FSR2/blob/1680d1edd5c034f88ebbbb793d8b88f8842cf804/src/ffx-fsr2-api/CMakeLists.txt) · [Pass declarations](https://github.com/GPUOpen-Effects/FidelityFX-FSR2/blob/1680d1edd5c034f88ebbbb793d8b88f8842cf804/src/ffx-fsr2-api/dx12/CMakeLists.txt) · [MIT license](https://github.com/GPUOpen-Effects/FidelityFX-FSR2/blob/1680d1edd5c034f88ebbbb793d8b88f8842cf804/LICENSE.txt)
- **Naga.** The compiler's checked-in SPIR-V snapshots and the entry points declared in its generated HLSL snapshot metadata. DXC uses the matching shader stage and promotes legacy Shader Model 5 profiles to 6.0. Failed entries are retried using its HLSL 2018 language mode. Native SPIR-V snapshots use the SPIR-V version declared in each file. Some tests correspond to the same logical input in both output formats. [Snapshot test docs](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/docs/testing.md) · [Apache-2.0](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/LICENSE.APACHE) · [MIT](https://github.com/gfx-rs/wgpu/blob/c76dea031c688ecef0050dbf60506fff128fb23f/LICENSE.MIT)

For every HLSL entry point, DXC emits Vulkan 1.2 SPIR-V at `-Od` and `-O3`. SPIRV-Tools validates each binary. A small set of SPIRV-Tools passes promotes local variables to inspectable SSA values and removes dead instructions on the early path. A separate `spirv-opt -O` run tests what survives later optimization on the optimized path. Both paths are also applied to native Naga SPIR-V. This is a CPU and static applicability census. Existing RTX readbacks concern the synthetic workload in the original study. [DXC SPIR-V backend](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/SPIR-V.rst) · [SPIR-V structured control flow and SSA](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html) · [Khronos optimizer](https://github.com/KhronosGroup/SPIRV-Tools#optimizer)

The scanner requires a structured `OpSwitch`, distinct arm entries reached only from its header, and either a direct return on each arm or a shared successor with a single candidate PHI result. It models identical relative internal dependencies using the existing planner. Differing inputs can be assigned to the same parameter column. Shift counts require a constant below 32 or an explicit mask of 31. It rejects a candidate with additional uses of the proposed moved instructions, unsupported arithmetic or decorations. Other control flow, memory effects inside the suffix, floating-point arithmetic, paths that join after several blocks, and opportunities that a frontend has already erased fall outside the census.

## Results

| Inputs | Validated / attempted | Early switches / directly joined arms | Final switches / directly joined arms | Eligible |
| --- | ---: | ---: | ---: | ---: |
| MiniEngine | 150 / 150 | 28 / 0 | 28 / 0 | 0 |
| FSR 2 | 16 / 16 | 52 / 42 | 12 / 0 | 0 |
| Naga-generated HLSL | 104 / 110 | 19 / 3 | 14 / 0 | 0 |
| Native Naga SPIR-V | 103 / 103 | 8 / 5 | 11 / 2 | 0 |
| Total | **373 / 379** | 107 / 50 | 65 / 2 | **0** |

The paired 270 usable DXC entry points account for 18.356 seconds when summing their three-run median `-O3` wall times, and zero of that total is in modules with an eligible switch. This is the measured share of compile work in eligible modules in this corpus. It does not measure time spent inside switch compilation or give an estimate for unseen generators. Six Naga-generated inputs failed validation or compilation in both modes and remain in the evidence as failures. Twelve other Naga inputs entered the census after recovery in HLSL 2018 mode. All 103 native Naga binaries, including outputs after promotion and the optimizer, had identical hashes when assembled with either v2026.4 at `g3c8fd352` or the documented v2026.5 build.

The synthetic PCG-32 baseline checked that the census can see a known opportunity. After promotion it had one 32-arm region with a 15-operation common suffix and one parameter column. DXC `-O3` reduced the suffix to 10 operations. SPIRV-Tools `-O` left that optimized binary byte-identical, and the explicitly factored control was smaller at 4,320 versus 10,520 bytes and had no remaining eligible region. The raw `-Od` control did not show the candidate until local variables were promoted. This comparison establishes why the early-IR scan matters and why a later optimizer alone can miss the pattern. The original study has the independent timing trials and GPU readback for this synthetic family.

No real corpus module reached the rewrite, so there is no paired real compile-time, peak-memory, PSO or GPU result to report for the transform. Measure frequent exact regions in a receiving emitter before extending this implementation. The open compiler snapshots and hand-written production shaders are a defensible screening population and do not sample live translated shader frequency.

## Prior work found during preflight

PortBridge's broad compiler inquiry surfaced XCL's repeated-code PR and TuxBox's existing DXC timeout fallback. An exact follow-up in PortBridge found XCL's alternative compact backend and its driver/stack constraints. Direct GitHub keyword search also surfaced the distinct nested-dispatch experiment. Its author reported a substantial cold driver-build gain on one large workload and a slowdown on one of the smaller tests. Those reports justify studying dispatch structure separately from repeated pure arithmetic. [XCL #1867](https://github.com/xcl-dev/xcl/pull/1867) · [TuxBox #23](https://github.com/brcly/TuxBox/pull/23) · [XCL #1316](https://github.com/xcl-dev/xcl/pull/1316) · [XCL #2025](https://github.com/xcl-dev/xcl/pull/2025)

## Reproduce

Clone each upstream repository and check out the exact commit linked above. The harness checks the revisions and working trees. It reads source files and compiles shaders without running upstream scripts. Use Python 3.11+, DXC 1.9.2609.5 and SPIRV-Tools 2026.5 at `g340b4c41` on PATH, or supply the executable paths. The [original study](README.md#reproduce) links the pinned SPIRV-Tools bundle.

```powershell
python -B -m unittest discover -s . -v
python -B corpus_benchmark.py --miniengine 'C:/code/DirectX-Graphics-Samples' --fsr2 'C:/code/FidelityFX-FSR2' --naga 'C:/code/wgpu' --rounds 3 --output corpus-results.json
```

The [JSON evidence](corpus-results.json) includes exact revisions, tool versions, stage output hashes and sizes, failures and compile observations. The compilation times include process startup and file output. Tests used an i5-13600KF on Windows 11. Background compiler work may affect the absolute timings. The applicability conclusion follows from the binaries and does not depend on a timing difference.
