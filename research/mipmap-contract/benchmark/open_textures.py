# SPDX-License-Identifier: MIT
"""Prepare pinned glTF textures and verify the Vulkan mipmap replay."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from shutil import copyfile
from urllib.request import urlopen

import numpy as np
from PIL import Image

from analyze import difference, record


ASSET_REF = "e124e8d8d7330a5372bc2b4d00d39a4a9d7997ea"
ASSET_URL = f"https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/{ASSET_REF}/Models/"
ASSETS = (
    ("fox-atlas", "Fox/glTF/Texture.png", 1024,
     "61c8b109ee7f8bf262791933380fafb1465f7b51cbe6472c2d21eff0b31f83a1",
     "5c57af2a041383fb32b9d6d81397400078107d0249ff91e65bc0eb38849782a2"),
    ("alpha-labels", "AlphaBlendModeTest/glTF/AlphaBlendLabels.png", 1024,
     "19c705f7e207384ca1ab01e0665601c051ca33c5848c03ce4fffad625b416b53",
     "f472d6ed8de13d4b9b6a147aadcb0e218b7077169397da773eece5ed6fb56758"),
    ("stained-glass", "StainedGlassLamp/glTF/StainedGlassLamp_grill_basecolor-alpha.png", 2048,
     "34ebdd2045586dae22edce1f5947414785a93cb3c7ac3e475435a6b8f4b2a0dc",
     "6732cfce6019662302c55ab09e84924f95d7a1223f858897b23bedd4d565748b"),
)
SHADER_SHA256 = "11eeb2346da6db04307919b2e83a9c618b09cb2ef8231f251524ce9fc0617058"


def prepare_inputs(scratch, upstream):
    scratch.mkdir(parents=True, exist_ok=True)
    for label, path, side, digest, decoded_digest in ASSETS:
        with urlopen(ASSET_URL + path, timeout=15) as response:
            encoded = response.read(3_000_000)
        if sha256(encoded).hexdigest() != digest:
            raise ValueError(f"{label} does not match the pinned PNG")
        with Image.open(BytesIO(encoded)) as image:
            if image.size != (side, side):
                raise ValueError(f"unexpected dimensions for {label}")
            raw = image.convert("RGBA").tobytes()
        if sha256(raw).hexdigest() != decoded_digest:
            raise ValueError(f"unexpected decoded bytes for {label}")
        (scratch / f"{label}.rgba").write_bytes(raw)

    # Keep physical subgroup lanes unchanged. Move both logical workgroup IDs
    # used by the fast shader to simulate one Vulkan-permitted permutation.
    destination = scratch / "permuted"
    destination.mkdir(exist_ok=True)
    for name in ("srgba8_mipmap_fast_pipeline.comp", "srgba8_mipmap_preamble.glsl"):
        copyfile(upstream / name, destination / name)
    path = "nvpro_pyramid.glsl"
    original = (upstream / path).read_bytes().replace(b"\r\n", b"\n")
    if sha256(original).hexdigest() != SHADER_SHA256:
        raise ValueError("expected the pinned NVIDIA pyramid shader")
    marker = b"layout(local_size_x = 256) in;"
    start = original.index(marker)
    end = original.index(b"#endif /* !NVPRO_USE_FAST_PIPELINE_ALTERNATIVE_ */", start)
    fast = original[start:end]
    fast = fast.replace(b"gl_LocalInvocationIndex", b"pbPermutedLocalIndex()")
    fast = fast.replace(b"gl_GlobalInvocationID.x", b"pbPermutedGlobalIndex()")
    mapping = b"""
uint pbPermutedLocalIndex()
{
  uint i = gl_LocalInvocationIndex;
  return i == 1u ? 4u : (i == 4u ? 1u : i);
}

uint pbPermutedGlobalIndex()
{
  return gl_WorkGroupID.x * gl_WorkGroupSize.x + pbPermutedLocalIndex();
}
"""
    (destination / path).write_bytes(original[:start] + fast.replace(marker, marker + mapping, 1) + original[end:])


def verify_readbacks(scratch):
    results = {}
    for label, path, side, digest, decoded_digest in ASSETS:
        stock_path = scratch / f"fixed-{side}-{side}-{label}"
        permuted_path = scratch / f"{stock_path.name}-permuted"
        baseline = record(stock_path, "fixed", side, side, label)
        remapped = record(permuted_path, "fixed", side, side, label)
        if baseline["base_sha256"] != decoded_digest or remapped["base_sha256"] != decoded_digest:
            raise ValueError(f"unmatched input for {label}")
        if baseline["readback_difference"]["different_bytes"]:
            raise ValueError(f"the unmodified stock shader and rewrite disagree for {label}")
        if baseline["readback_sha256"]["rewritten"] != remapped["readback_sha256"]["rewritten"]:
            raise ValueError(f"the rewrite does not reproduce for {label}")

        stock = np.fromfile(stock_path / "automatic.rgba", dtype=np.uint8)
        remapped_stock = np.fromfile(permuted_path / "automatic.rgba", dtype=np.uint8)
        delta = difference(stock, remapped_stock)
        if not delta["different_bytes"]:
            raise ValueError(f"the permutation negative control did not affect {label}")
        alpha = np.fromfile(stock_path / "base.rgba", dtype=np.uint8)[3::4]
        results[label] = {
            "asset": path,
            "asset_sha256": digest,
            "input_alpha_counts": {
                "transparent": int(np.count_nonzero(alpha == 0)),
                "translucent": int(np.count_nonzero((alpha > 0) & (alpha < 255))),
                "opaque": int(np.count_nonzero(alpha == 255)),
            },
            "baseline": baseline,
            "permuted_stock": {key: value for key, value in remapped.items() if "microseconds" not in key},
            "permutation_effect": delta,
            "permutation_changed_alpha": int(np.count_nonzero(stock[3::4] != remapped_stock[3::4])),
        }
    return {"glTF_sample_assets_revision": ASSET_REF, "textures": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("--prepare-from", type=Path, metavar="NVPRO_PYRAMID_DIR",
                        help="download the pinned inputs and prepare a stock shader negative control")
    args = parser.parse_args()
    if args.prepare_from is not None:
        prepare_inputs(args.scratch, args.prepare_from)
    else:
        print(json.dumps(verify_readbacks(args.scratch), indent=2))


if __name__ == "__main__":
    main()
