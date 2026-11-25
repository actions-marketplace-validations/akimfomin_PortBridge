"""Analyze paired timestamp traces and raw outputs from the headless mipmap replay."""

import argparse
import hashlib
import json
from pathlib import Path
import re
from statistics import median

import numpy as np


DIMS = re.compile(r"(result|fixed)-(\d+)-(\d+)-(hashed|constant)")


def reduce_axis(image, axis):
    """Integrate a box over nonoverlapping equal-area destination intervals."""
    source = np.moveaxis(image, axis, 0)
    size = source.shape[0]
    if size == 1:
        return image
    half = size // 2
    if size % 2 == 0:
        averaged = 0.5 * (source[0::2] + source[1::2])
    else:
        x = np.arange(half)[:, None, None]
        averaged = ((half - x) * source[0:-1:2]
                    + half * source[1::2]
                    + (x + 1) * source[2::2]) / size
    return np.moveaxis(averaged, 0, axis)


def as_linear(encoded):
    image = encoded.astype(np.float64) / 255
    rgb = image[..., :3]
    rgb[:] = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    return image


def as_srgb(linear):
    color = linear.copy()
    rgb = color[..., :3]
    rgb[:] = np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * rgb ** (1 / 2.4) - 0.055)
    return np.floor(np.clip(color, 0, 1) * 255 + 0.5).astype(np.uint8)


def area_reference(base, width, height, *, round_each_level):
    linear = as_linear(base.reshape(height, width, 4))
    results = []
    while linear.shape[:2] != (1, 1):
        linear = reduce_axis(reduce_axis(linear, 0), 1)
        encoded = as_srgb(linear)
        results.append(encoded.ravel())
        if round_each_level:
            linear = as_linear(encoded)
    return np.concatenate(results)


def difference(first, second):
    if first.shape != second.shape:
        raise ValueError("readbacks have different lengths")
    delta = np.abs(first.astype(np.int16) - second.astype(np.int16))
    return {"different_bytes": int(np.count_nonzero(delta)), "max_abs_difference": int(delta.max())}


def record(path, family, width, height, pattern):
    names = ("automatic", "rewritten") if family == "fixed" else ("general", "automatic")
    logs = (path / "timings.csv").read_text().splitlines()
    expected_size = sum(
        max(1, width >> level) * max(1, height >> level) * 4
        for level in range(1, max(width, height).bit_length())
    )
    pairs = {name: {} for name in names}
    for row in logs[1:]:
        name, index, microseconds = row.split(",")
        index = int(index)
        if index in pairs[name]:
            raise ValueError("duplicate timing index")
        pairs[name][index] = float(microseconds)
    if set(pairs[names[0]]) != set(pairs[names[1]]) or not pairs[names[0]]:
        raise ValueError("incomplete timing pairs")
    first, second = [
        [by_index[i] for i in sorted(by_index)] for by_index in pairs.values()
    ]
    if any(value <= 0 for value in first + second):
        raise ValueError("invalid timestamp interval")
    base = np.fromfile(path / "base.rgba", dtype=np.uint8)
    if base.size != width * height * 4:
        raise ValueError("unexpected base size")
    images = {name: np.fromfile(path / f"{name}.rgba", dtype=np.uint8) for name in names}
    if any(image.size != expected_size for image in images.values()):
        raise ValueError("unexpected mip-chain length")

    info = {
        "width": width,
        "height": height,
        "input": pattern,
        "fixed_full_wave32": family == "fixed",
        "adapter_line": logs[0],
        "mip_bytes_per_variant": expected_size,
        "base_sha256": hashlib.sha256(base).hexdigest(),
        "readback_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in images.items()},
        "readback_difference": difference(*images.values()),
        "median_microseconds": dict(zip(names, [median(first), median(second)])),
        "paired_second_minus_first_median_microseconds": round(median(b - a for a, b in zip(first, second)), 6),
        "timing_pairs_microseconds": list(zip(first, second)),
    }
    if max(width, height) <= 512:
        info["cpu_area_reference"] = {}
        for label, each_level in (("unrounded_until_storage", False), ("round_each_level", True)):
            ref = area_reference(base, width, height, round_each_level=each_level)
            info["cpu_area_reference"][label] = {
                name: difference(data, ref) for name, data in images.items()
            }
            if pattern == "constant" and any(
                diff["different_bytes"] for diff in info["cpu_area_reference"][label].values()
            ):
                raise ValueError("constant case changed color")
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="parent of result-W-H-input / fixed-W-H-input directories")
    args = parser.parse_args()
    observed = {}
    for path in sorted(args.results.iterdir()):
        match = DIMS.fullmatch(path.name)
        if match is not None and path.is_dir():
            family, width, height, pattern = match.groups()
            observed[path.name] = record(path, family, int(width), int(height), pattern)
    if not observed:
        parser.error("no named result directories found")
    print(json.dumps(observed, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
