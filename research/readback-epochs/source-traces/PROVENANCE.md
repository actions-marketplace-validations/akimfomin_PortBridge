# Open call-shape controls for adaptive readback

This directory has CPU-only capture harnesses, exact Git pins and synthetic replay inputs. The harnesses do not load GPU drivers or launch the full browser apps. The captures record commands or sampled addresses from upstream consumer methods under a controlled environment. Vulkan replay values come from PortBridge's deterministic integer producer.

## HeatTransfer

- Source [OpenLyceum/HeatTransfer at 8d6bcecb](https://github.com/OpenLyceum/HeatTransfer/tree/8d6bcecb643772730fc1ebacd3e0eba2aea7066c).
- Upstream [license declaration](https://github.com/OpenLyceum/HeatTransfer/blob/8d6bcecb643772730fc1ebacd3e0eba2aea7066c/package.json#L19) is AGPL-3.0-or-later. Original TypeScript is fetched separately during capture. The captured records contain dimensions, call counts and command sizes.
- [Stepping and readback](https://github.com/OpenLyceum/HeatTransfer/blob/8d6bcecb643772730fc1ebacd3e0eba2aea7066c/src/common/field/gpu/WebGpuFieldEngine.ts#L519-L647), [workgroup size](https://github.com/OpenLyceum/HeatTransfer/blob/8d6bcecb643772730fc1ebacd3e0eba2aea7066c/src/common/field/gpu/shaders/common.ts#L165), [diffusion output store](https://github.com/OpenLyceum/HeatTransfer/blob/8d6bcecb643772730fc1ebacd3e0eba2aea7066c/src/common/field/gpu/shaders/compute.ts#L135-L158) and [presets](https://github.com/OpenLyceum/HeatTransfer/blob/8d6bcecb643772730fc1ebacd3e0eba2aea7066c/src/HeatTransferConstants.ts#L71-L89).
- `capture_heat.mjs` extracts the exact `step` and `requestReadback` methods under Node v24 type stripping and executes them with a mocked WebGPU device. Diffusion is active and recorded as a full logical-field overwrite. The source alternates two textures. The normalized buffer represents the latest temperature generation. It preserves every readback request present in the mock capture.
- The 128² and 2048² presets each have 48 writes and 12 full readbacks with prompt mock completion. A 5-step injected outstanding mapping delay on the 2048² preset yields 6 readbacks. These counts define synthetic scheduling fixtures. They are not physical adapter observations. If the target adapter caps the requested grid size, the application uses fewer cells.
- One read transfers exactly 65,536 bytes at 128² and 16,777,216 at 2048². In this diffusion case every newly requested snapshot is dirty. Reuse is exactly zero. The fixture is a control for full-range selection and no-read steps.

## SNOWFLOW

- Source [Ditto190/snowflow_demo_webGPU_unreal5 at 54503973](https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/tree/545039733b74eec742862f161990142c7ca7c7ec).
- [MIT license](https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/blob/545039733b74eec742862f161990142c7ca7c7ec/LICENSE) by Maksymilian Dendura. Original source is fetched separately. This work does not incorporate visual assets.
- [Stock initialization](https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/blob/545039733b74eec742862f161990142c7ca7c7ec/src/terrain/heightfield.js#L54-L162), [height and normal sampling](https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/blob/545039733b74eec742862f161990142c7ca7c7ec/src/terrain/heightfield.js#L169-L212) and [character observations](https://github.com/Ditto190/snowflow_demo_webGPU_unreal5/blob/545039733b74eec742862f161990142c7ca7c7ec/src/character/controller.js#L116-L150).
- `capture_snowflow.mjs` executes the upstream `_readback`, `heightAt`, `normalAt` and `CharacterController` with the original damping helper. The Babylon vector, input and rig interfaces have small local substitutes. Texture values are generated at capture time. Two scripted 240-frame paths exercise walk, sprint, surf and braking.
- The original initialization called `readPixels(0,0)` once, with a 128 MiB RG32F mock result. The real backend can widen the returned stride. The stock algorithm computes a half-resolution 16 MiB red-channel mirror and scans the full mirror to determine global height limits. That one-shot stock readback has no reuse. The separate Vulkan fixture isolates the transfer shape rather than executing those reductions.
- The two grounding routes record 24,384 actual indexed JavaScript loads each. Multiple reads inside one frame coalesce to a single demand for each unique word. Primary and holdout request 31,104 and 31,056 bytes across all frames at this granularity. Page-rounding these exact same addresses to 4 KiB inflates demand to 9,863,168 and 5,906,432 bytes.
- A deferred readback from a persistent half-resolution GPU field is a **counterfactual**. The normal application has already read the complete source and its grounding consumes only CPU memory. The counterfactual cost model omits startup box reduction, global min/max, and possible changes to callbacks or GPU layout. It is useful as an upper-bound locality trace and a check against exaggerating wins from 4 KiB rounding. It establishes neither a stock app speedup nor a startup replacement.

## Reproduction

From an isolated folder with the three capture scripts present:

```powershell
git clone https://github.com/OpenLyceum/HeatTransfer.git heat
git -C heat checkout 8d6bcecb643772730fc1ebacd3e0eba2aea7066c
git clone https://github.com/Ditto190/snowflow_demo_webGPU_unreal5.git snow
git -C snow checkout 545039733b74eec742862f161990142c7ca7c7ec
node capture_heat.mjs heat heat-capture.json
node capture_snowflow.mjs snow snowflow-capture.json
python -B make_app_traces.py generated
```

The scripts read the pinned source via `git show` and record source hashes in the raw capture JSON. `generated/workload-shapes.json` has ordered logical byte-range events and separate exact-byte counts. `generated/*.tsv` uses the original PortBridge replay grammar and includes a legacy three-sample checksum plus offline ideal deltas. The adaptation can derive online deltas only from past and current events. `generated/census.json` records requested and objectively reusable volume. Empty read lists are significant, and new addresses cannot be inferred before their observation.
