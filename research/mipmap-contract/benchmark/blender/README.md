# Stock Blender Vulkan mipmap replay

This replay measures the mipmap path in the official Blender 5.3.0 release build. It uses ordinary image acquisition from Blender's Python API and per-level GPU readback. The partial painting path is outside the measured workload.

## Production baseline

The tested Windows ZIP uses build `02f0899d78e3` and has SHA-256 `1937910e5ecd7575c7d5ce496b84af57a45e238835979d0b08f2ce4072877ef1`. The host implementation has Git blob `7cf9475a2fc9d65ddab4baea5b8016651693c1ff` in this build and in Blender main at `eb6054b80e9190584f9dce3c0ca2f48278225f07`. It already includes sRGB in-place writes, partial painting updates in 256 × 256 chunks, and one set of level views across all layers within each full regeneration. The maintainer reported the mipmap update at under 2% of CPU overhead in a preliminary 5 × 8K UDIM painting case. [Official Blender build](https://cdn.builder.blender.org/download/daily/blender-5.3.0-stable%2Bv53.02f0899d78e3-windows.amd64-release.zip) · [Build's host implementation](https://github.com/blender/blender/blob/02f0899d78e374b63e7181d9061e1f7ab03419cc/source/blender/gpu/intern/gpu_texture_mipmap.cc) · [Main's matching blob](https://projects.blender.org/api/v1/repos/blender/blender/contents/source/blender/gpu/intern/gpu_texture_mipmap.cc?ref=eb6054b80e9190584f9dce3c0ca2f48278225f07) · [Upstream #161392](https://projects.blender.org/blender/blender/pulls/161392)

The cold arm clears the GPU texture cache with `Image.gl_free()` outside timing. Both arms acquire a texture via `gpu.texture.from_image()`. On a cold load that function reaches `IMB_acquire_gpu_texture()`, which calls `GPU_texture_update_mipmap_chain()` after creating the texture. Decode, rescale, synthetic fixture generation, and device initialization happen before the timed arms. Shader compilation and first-use driver work are warmed up separately. The two cache orders and the two texture orders alternate. [Image texture path](https://github.com/blender/blender/blob/02f0899d78e374b63e7181d9061e1f7ab03419cc/source/blender/imbuf/intern/util_gpu.cc#L779-L823)

The Vulkan trace records the native `Update Mipmaps` CPU scope. That event covers the production update function after built-in shader lookup. Blender's Vulkan implementation adds these events only to the CPU track. The separate wall interval includes texture acquisition, queued uploads and mipmap computation, a small probe dispatch, and synchronization with its 256-byte readback. GPU event timings and CPU time exclusive of waits cannot be recovered from that wall interval. [Trace implementation](https://github.com/blender/blender/blob/02f0899d78e374b63e7181d9061e1f7ab03419cc/source/blender/gpu/vulkan/vk_debug.cc#L65-L93)

## Observations

Vulkan on the RTX 4070 Ti SUPER, NVIDIA 617.14. There were 18 cold/hot pairs per texture and two warmup pairs per texture. Exactly 40 native CPU mipmap events were recorded, one per cold arm including warmup. For every arm the probe checks one texel per level and the actual number of levels. Results repeat across all arms. The synthetic positive levels independently match the expected linear average of a two-by-two checker within the sRGB quantization tolerance.

| Image | Levels | Cold texture acquisition | Native CPU mip scope | Native CPU scope share of acquisition | Cold through synchronized probe |
| --- | ---: | ---: | ---: | ---: | ---: |
| Khronos Water Bottle PNG scaled to 1024 × 1024 | 11 | 567.55 µs | 50.5 µs | 9.141% | 1.177 ms |
| Generated 4096 × 4096 RGBA parity checker | 13 | 20.449 ms | 76.5 µs | 0.390% | 25.989 ms |

Durations use medians. Shares are medians of per-trial ratios. Acquisition measures elapsed host time. Device-wide activity sampled immediately before and after the run was 47% and 67% GPU utilization respectively. Readback wall times varied, including in the cache hits. The 1024 cache hit median through synchronized probe exceeded the cold median. The cold/cache control proves which path was taken and provides context for the CPU scope. A candidate implementation, texture painting stroke, or isolated GPU duration requires its own measurement. These results bound how much removing this measured host scope alone could help these cold loads, even if it were entirely eliminated.

## Reproduction

Download the CC0 source separately, then verify SHA-256 `62d0ad9b4e2c75e9bc7d67644a50d697563000ffa586d2e185ea38f5000e0a63`. Source attribution is Microsoft, Water Bottle asset in Khronos glTF Sample Assets, pinned to `e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea`. The replay resizes its original 2048 × 2048 PNG in Blender. The other input is generated in memory. [Pinned texture](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea/Models/WaterBottle/glTF/WaterBottle_baseColor.png) · [Asset license](https://github.com/KhronosGroup/glTF-Sample-Assets/blob/e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea/Models/WaterBottle/LICENSE.md)

From a fresh output folder run the official binary in background mode. Set `BLENDER_USER_RESOURCES` to an isolated writable folder if running alongside an installed Blender.

```text
blender --background --factory-startup --gpu-backend vulkan --debug-gpu-backend-no-fallback --profile-gpu --python-exit-code 1 --python app_mipmap_replay.py -- WaterBottle_baseColor.png samples.json 18
python analyze_app_mipmap.py samples.json profile.json summary.json
```

The replay raises an error if the Vulkan backend, source hash, expected dimensions, number of mip levels, or the checker result fails validation. Use samples.json and profile.json from the same fresh output folder and run. The analyzer checks that the profile contains one CPU mipmap event per cold load and that each event fits its paired acquisition interval.
