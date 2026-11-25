# Portable lane ordering for mipmap generation

Blender's GPU mipmap implementation uses a general compute shader and caps a dispatch at two levels. The NVIDIA sample offers both a general shader and a faster shuffle-based path. In NVIDIA's published 4,096 × 4,096 sRGBA8 benchmark on an RTX 3090, the library took 112.000 µs and one blit per level took 159.744 µs. AMD FidelityFX SPD provides a separate mature implementation. Its own edge handling and filter contract matter when choosing a reference. [Blender's two-level dispatch](https://github.com/blender/blender/blob/82f4325bf96ddf50b449cee63518d184eafbb469/source/blender/gpu/intern/gpu_texture_mipmap.cc#L139-L147) · [NVIDIA comparison](https://github.com/nvpro-samples/vk_compute_mipmaps/blob/6c248f554e91329875e9860f2258019a32b44ee9/README.md#parallelization-strategy) · [AMD SPD](https://github.com/GPUOpen-Effects/FidelityFX-SPD/tree/7c796c6d9fa6a9439e3610478148cfd742d97daf)

## A missing portability guarantee

The pinned fast shader chooses the logical source tile and its local offsets with `gl_GlobalInvocationID.x` and `gl_LocalInvocationIndex`. Its shuffle instructions and write leaders use subgroup lane IDs. Vulkan specifies no direct relationship between the two numberings. This matters even in a full subgroup. [Tile indexing](https://github.com/nvpro-samples/vk_compute_mipmaps/blob/6c248f554e91329875e9860f2258019a32b44ee9/nvpro_pyramid/nvpro_pyramid.glsl#L402-L430) · [Shuffle and write leader](https://github.com/nvpro-samples/vk_compute_mipmaps/blob/6c248f554e91329875e9860f2258019a32b44ee9/nvpro_pyramid/nvpro_pyramid.glsl#L359-L396) · [Vulkan built-in definitions](https://docs.vulkan.org/spec/latest/chapters/interfaces.html#interfaces-builtin-variables-sgli)

A counterexample uses two active four-lane tiles in a full workgroup. Exchange the native local indices assigned to physical lanes 1 and 4. Lane 0 still leads the first tile. Its XOR lookup for the next sample now reads logical invocation 4 from the other tile, where the original filter expects invocation 1. The same valid permutation breaks the unqualified assumption at full Wave32 or Wave64. This is a model showing software depends on unspecified ordering. It does not establish a failure on a particular GPU.

The rewrite reconstructs a logical index using `SubgroupId * SubgroupSize + SubgroupLocalInvocationId`, as described in the Vulkan specification for full subgroups. The same index now drives tile assignment, source coordinates and workgroup shared-memory indexing. With full groups of fixed width 32 or 64, each XOR mask stays inside its aligned group of participating logical lanes. The modeled last workgroup can contain fewer active tiles. Each such tile still has all required shuffle sources. The highest-depth path reads the first four logical lanes after its workgroup barrier. The proof models ownership and source indices. It does not prove arithmetic identity between different filter or storage formats. [Vulkan full subgroups](https://docs.vulkan.org/spec/latest/chapters/shaders.html#shaders-full-subgroups) · [Tests](test_mipmap_contract.py)

## Selecting a schedule

[mipmap_contract.py](mipmap_contract.py) propagates exact half-open dirty rectangles for this separable filter's tap footprint. An even axis uses two taps, an odd axis uses three and an axis at length one stays unchanged. `required_source` computes the corresponding source rectangle, including unchanged neighbors. A partial plan requires valid texels retained outside the dirty area of the existing chain. It uses one level per logical pass. Layered textures cannot use the unlayered NVIDIA wrapper. [Blender filter footprint](https://github.com/blender/blender/blob/82f4325bf96ddf50b449cee63518d184eafbb469/source/blender/gpu/shaders/gpu_shader_update_mipmaps.bsl.hh#L140-L143) · [Odd-axis weights](https://github.com/blender/blender/blob/82f4325bf96ddf50b449cee63518d184eafbb469/source/blender/gpu/shaders/gpu_shader_update_mipmaps.bsl.hh#L285-L289)

For full single-layer updates, the planner searches legal sequences and minimizes the number of logical passes. For the shuffle path, the pinned NVIDIA limits are an extent divisible by four and by each fused level's tile size, at most six levels per dispatch, a 256-invocation workgroup, a 16-element image-view array, and a dispatch count within the device limit. The caller also vouches for compatible sampled/storage views, valid formats and required subgroup features at the selected width. Set `max_local_x` to the minimum of the device X size and invocation limits and, when required subgroup size is used, the corresponding maximum subgroup count times width. The general path uses at most two levels per pass. The model does not encode graph API barriers, translate texture painting chunks, or count backend splits. [Official dispatcher and limits](https://github.com/nvpro-samples/vk_compute_mipmaps/blob/6c248f554e91329875e9860f2258019a32b44ee9/nvpro_pyramid/nvpro_pyramid_dispatch.hpp#L195-L291)

All fused choices require an explicit numeric premise from the caller. The synthesis can pass intermediate values through registers or shared memory while the output image has already undergone a format conversion or quantization. An unverified numeric contract stays on the one-level path. In the admitted 4,096 × 4,096 example, the planner covers 12 output levels in two passes of six, versus six passes at a two-level cap. That is a count in the model. The measured comparison used the original NVIDIA shaders and the rewrite with matching host flags. [Benchmark and limits](benchmark/README.md)

## Reproduction

Run the Python tests from the PortBridge root. The exact dirty-region tests compare against brute-force tap intersection. The lane tests cover each supported depth and active tile count at widths 32 and 64.

```sh
python -B -m unittest discover -s research/mipmap-contract -v
```

To build the rewrite, use the Apache-2.0 NVIDIA sample at `6c248f554e91329875e9860f2258019a32b44ee9`, copy the shader files from its `nvpro_pyramid` directory to a separate directory, and replace that copy of `nvpro_pyramid.glsl`. The rewrite checks the normalized source SHA-256 `11eeb2346da6db04307919b2e83a9c618b09cb2ef8231f251524ce9fc0617058`. The non-fast branch is preserved byte-for-byte after line-ending normalization.

```sh
python research/mipmap-contract/mipmap_contract.py rewrite <upstream/nvpro_pyramid.glsl> <copy/nvpro_pyramid.glsl>
glslangValidator -V --target-env vulkan1.1 <copy/srgba8_mipmap_fast_pipeline.comp> -o fast.spv
spirv-val --target-env vulkan1.1 fast.spv
```

Khronos glslang 16.6.0 and SPIRV-Tools v2026.4-119 validated the rewritten shader. The recorded binary SHA-256 is `87cd7e39918dfec37733dc91596c4235ef52306783dd93c4d8234275b0a8b650`. To run it, the Vulkan device needs the full-subgroup feature and the host must create a fixed-width compute pipeline with full subgroups. The hardware reproduction uses Wave32 and records its checks separately.
