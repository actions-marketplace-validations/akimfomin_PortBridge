# SPDX-License-Identifier: MIT
"""Reproduce stock Blender mipmap CPU profile on two full image loads.

Run with Blender 5.3.0, --background --factory-startup --gpu-backend vulkan
--debug-gpu-backend-no-fallback --profile-gpu --python-exit-code 1
--python app_mipmap_replay.py -- WaterBottle_baseColor.png output.json 12
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import bpy
import gpu
import numpy as np

INPUT_SHA256 = "62d0ad9b4e2c75e9bc7d67644a50d697563000ffa586d2e185ea38f5000e0a63"
PROBE_LENGTH = 16
PROBE_SOURCE = """
void main()
{
    const int level = int(gl_GlobalInvocationID.x);
    const int levels = textureQueryLevels(subject);
    if (level == 15) {
        imageStore(probe, ivec2(level, 0), vec4(float(levels), 0.0, 0.0, 1.0));
        return;
    }
    if (level >= levels) {
        imageStore(probe, ivec2(level, 0), vec4(-1.0));
        return;
    }
    const ivec2 extent = textureSize(subject, level);
    vec4 sample_value = texelFetch(subject, ivec2(extent.x / 2, extent.y / 3), level);
    imageStore(probe, ivec2(level, 0), sample_value);
}
"""


def build_probe():
    info = gpu.types.GPUShaderCreateInfo()
    info.sampler(0, "FLOAT_2D", "subject")
    info.image(1, "RGBA32F", "FLOAT_2D", "probe", qualifiers={"WRITE"})
    info.local_group_size(PROBE_LENGTH)
    info.compute_source(PROBE_SOURCE)
    shader = gpu.shader.create_from_info(info)
    output = gpu.types.GPUTexture((PROBE_LENGTH, 1), format="RGBA32F")
    return shader, output


def make_cases(png_path):
    if sha256(png_path.read_bytes()).hexdigest() != INPUT_SHA256:
        raise ValueError("Khronos WaterBottle PNG does not match the pinned input")
    water = bpy.data.images.load(str(png_path))
    if tuple(water.size) != (2048, 2048):
        raise ValueError(f"Unexpected source resolution {tuple(water.size)}")
    water.scale(1024, 1024)

    size = 4096
    pattern = np.empty((size, size, 4), dtype=np.float32)
    parity = (np.arange(size, dtype=np.uint16) & 1).astype(np.float32)
    pattern[..., 0] = parity[np.newaxis, :]
    pattern[..., 1] = parity[:, np.newaxis]
    pattern[..., 2] = np.not_equal(parity[:, np.newaxis], parity[np.newaxis, :])
    pattern[..., 3] = 1
    checker = bpy.data.images.new("Generated parity RGBA", size, size, alpha=True,
                                  float_buffer=False)
    checker.pixels.foreach_set(pattern.ravel())
    checker.update()
    return {"water_bottle_1024": water, "checker_4096": checker}


def check_mips(values, image, synthetic):
    expected_levels = max(image.size).bit_length()
    if values[15, 0] != expected_levels:
        raise ValueError(f"Expected {expected_levels} mip levels, got {values[15, 0]}")
    if not np.all(np.isfinite(values[:expected_levels])):
        raise ValueError("Non-finite texel")
    if synthetic and not np.allclose(values[1:expected_levels, :],
                                    (0.5, 0.5, 0.5, 1.0), atol=0.01, rtol=0):
        raise ValueError(f"Unexpected linear checker average: {values[:expected_levels]}")
    return expected_levels


def sample(case, image, cache, shader, output, previous, warmup, pair):
    if cache == "cold":
        image.gl_free()
    acquire_begin = perf_counter_ns()
    subject = gpu.texture.from_image(image)
    acquire_end = perf_counter_ns()
    shader.bind()
    shader.uniform_sampler("subject", subject)
    shader.image("probe", output)
    gpu.compute.dispatch(shader, 1, 1, 1)
    readback = output.read()
    through_probe = perf_counter_ns()
    if (subject.width, subject.height) != tuple(image.size) or subject.format != "SRGB8_A8":
        raise ValueError(f"Unexpected source format {subject.format} or dimensions")
    values = np.asarray(readback.to_list(), dtype=np.float32).reshape(PROBE_LENGTH, 4)
    levels = check_mips(values, image, case == "checker_4096")
    signature = sha256(values.tobytes()).hexdigest()
    if case in previous and not np.array_equal(previous[case], values):
        raise ValueError(f"Texture sample changed across cache arms for {case}")
    previous[case] = values
    return {"case": case, "cache": cache, "warmup": warmup, "pair": pair,
            "acquire_cpu_us": (acquire_end - acquire_begin) / 1000,
            "synchronized_with_probe_us": (through_probe - acquire_begin) / 1000,
            "probe_sha256": signature, "checked_levels": levels}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source_png", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("pairs", type=int, default=12, nargs="?")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    if args.pairs < 1:
        raise ValueError("Expected at least one pair")
    if bpy.app.build_hash.decode("ascii") != "02f0899d78e3":
        raise ValueError("Expected pinned 5.3.0 build 02f0899d78e3")
    gpu.init()
    device = {"backend": gpu.platform.backend_type_get(),
              "renderer": gpu.platform.renderer_get(),
              "driver": gpu.platform.version_get(),
              "vendor": gpu.platform.vendor_get(),
              "device_type": gpu.platform.device_type_get()}
    print(f"DEVICE {device}", flush=True)
    if device["backend"] != "VULKAN":
        raise ValueError("Vulkan backend was not selected")
    shader, output = build_probe()
    cases = make_cases(args.source_png)
    previous = {}
    rows = []
    for names_index, pair in enumerate(range(-2, args.pairs)):
        names = tuple(cases)
        if names_index % 2:
            names = names[::-1]
        for case in names:
            arms = ("cold", "hot") if pair < 0 or pair % 2 == 0 else ("hot", "cold")
            for arm in arms:
                row = sample(case, cases[case], arm, shader, output, previous, pair < 0, pair)
                rows.append(row)
                print(f"CHECK {pair} {case} {arm} {row['probe_sha256'][:12]} "
                      f"{row['acquire_cpu_us']:.1f} us acquire "
                      f"{row['synchronized_with_probe_us']:.1f} us through probe", flush=True)
    contents = {"blender_build": bpy.app.build_hash.decode("ascii"), "device": device,
                "pairs": args.pairs, "samples": rows, "source_png_sha256": INPUT_SHA256,
                "probe_values": {key: values.tolist() for key, values in previous.items()}}
    args.output_json.write_text(json.dumps(contents, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
