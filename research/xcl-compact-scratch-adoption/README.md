# XCL scratch reuse review handoff

The [XCL #2126 merge](https://github.com/xcl-dev/xcl/commit/afc5ee86ae3a9521c9f15d96505cd73fe72f2191) is the baseline. Kalmarv authored the persistent payload change and ivall merged it. The PortBridge reuse allocator remains a separate follow-up. ettehn independently applied the original PortBridge candidate to the older `f6fa8a9` head and reported 47,712 → 20,064 DWORDs per group in one translation, with 12 valid pieces both ways. Eight split tests passed with zero skips on a physical RTX 5070 Ti Laptop. The unnamed record did not supply execution or driver timing and cannot close the request for the three specific workloads. [Author's request](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7157104814) · [Independent report](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7162128623) · [Merge report](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7164031767)

## Recreate the review candidate

- Baseline `afc5ee86ae3a9521c9f15d96505cd73fe72f2191`
- Locally tested clean commit `0d002f1941d1bed0102c19f60ede150f1cfac668` on `codex/xcl-compact-scratch`
- [Public fork commit](https://github.com/akimfomin/xcl/commit/b3f7ab5574c4489761141e2de0ce31d2eb216412) has the same Git tree as the tested commit. [Compare against the verified merge base](https://github.com/xcl-dev/xcl/compare/afc5ee86ae3a9521c9f15d96505cd73fe72f2191...b3f7ab5574c4489761141e2de0ce31d2eb216412)
- [Candidate patch](xcl-compact-scratch-on-afc5ee86.patch), SHA-256 `18e20d785ad6788f0fb30e823de0e14c3b49b3fae40f3d4a42b043f2a108d99f`

The patch also passed `git apply --check` at the later main snapshot `06c9f5505f63f10c5ec49ef932d75b2c28177324`. That snapshot adds an unrelated file change. The build and hardware run below remain pinned to the original candidate. [Later main snapshot](https://github.com/xcl-dev/xcl/commit/06c9f5505f63f10c5ec49ef932d75b2c28177324)

Use a disposable XCL checkout at the baseline, a compatible Windows Rust toolchain, and DXC/DXIL 1.8 or newer. Verify before applying and select the physical adapter for coverage.

```powershell
git apply --check $CompactPatch
git apply $CompactPatch
cargo test --locked -p xcl --lib gpu::dxil::module::split::tests -- --test-threads=1 --nocapture
```

The 10 tests passed on a physical RTX 4070 Ti SUPER without skips. They cover the 256-DWORD open Wave32 fixture, the allocator boundary, oversized loops, and output readbacks. Replaying the same assertion with the merged base's original fixed allocator observed 288 DWORDs and failed as expected. [Verification details](verification.json)

The owner opened [draft XCL #2322](https://github.com/xcl-dev/xcl/pull/2322). nnonno91 independently passed 10 targeted tests on each of Radeon Graphics and RTX 5090 at the exact public SHA, with zero skips. The local open workspace on RTX 4070 Ti SUPER reported 1,265 passed, 0 failed, and 46 ignored with 27 runtime skip lines. The paired retail `xcl-smoke` blocks remain pending. [Independent report](https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7165250326) · [Current evidence](PR-READY.md) · [XCL contribution rules](https://github.com/xcl-dev/xcl/blob/06c9f5505f63f10c5ec49ef932d75b2c28177324/CONTRIBUTING.md)

## Pending aggregate comparison

The receiving team can run this on its existing authorized setup. Prepare exact baseline and candidate builds from the revisions under review, with the same split policy, adapter, driver and cache settings. Use the baseline and candidate separately and keep cached artifacts distinct. When needed, [the optional scratch probe](scratch-aggregate.patch) applies to both. It prints only piece count and scratch DWORDs per group when `XCL_SCRATCH_AGGREGATE=1`. Remove or disable the probe before timing.

Capture `ef008c0f` early-exit and late-shading, `c3ae6819` representative, and `fb1c6d2d` representative. Use matched grids and reference outputs. Timestamp the entire dispatch chain including internal barriers. Warm up for three seconds. Take four alternating paired rounds of twenty measurements per build and input. Record eight JSON Lines rows with these fields.

```text
case input build grid pieces scratch_dwords_per_group words_checked different_words gpu_us_rounds
```

Use build labels `baseline` and `candidate`. `gpu_us_rounds` contains four arrays of twenty GPU times in microseconds. [The merged-head comparator](compare_merged.py) verifies the same piece count, grid and checked word count for each pair. It records the baseline and candidate revisions and accepts the measured merged baseline counts.

```powershell
python -I -B compare_merged.py measurements.jsonl --candidate-revision $Candidate
```

Review the printed summary before sharing, adding the GPU, driver and build configuration. The shared artifact contains only aggregate data. Keep the shaders, raw timing rows, input and output buffers and internal logs in the receiving team's environment. An output mismatch or scratch growth makes the comparison return exit 1. Malformed data or a changed plan returns exit 2.

The [GPL-2.0-only notice](LICENSE-GPL-2.0-only) applies to the XCL patches. The Python comparator retains [MIT](LICENSE-MIT).
