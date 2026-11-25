# Recompiler: reuse scratch slots across disjoint payload lifetimes

Part of #1269. This follows #2126, which is merged. Keep Kalmarv's persistent scratch payload and lazy restores and reuse a slot once the last destination carrying its previous value has finished. Keep the original fixed offsets when reuse does not reduce stride.

[Fork candidate](https://github.com/akimfomin/xcl/tree/codex/compact-scratch-afc5ee8) at `b3f7ab5574c4489761141e2de0ce31d2eb216412` has the exact Git tree tested below.

**What is in it**

- `crates/xcl/src/gpu/dxil/module/split.rs` adds the PortBridge lifetime allocator, checks the inclusive last-consumer boundary, and makes the existing Wave32 fixture assert actual compaction. The merged oversized-loop variants keep their GPU readback checks.
- `THIRD_PARTY.md` records the origin and GPL-2.0-only license of the PortBridge patch. [Published PortBridge candidate](https://github.com/akimfomin/PortBridge/tree/89884212b8a5718f44b16b66e8df0cf5f263306b/research/xcl-2126-stacked-candidate)

**Tested**

- Windows 11 Pro build 28000, Intel Core i5-13600KF, RTX 4070 Ti SUPER driver 617.14, Rust 1.100.0 gnullvm, DXC/DXIL 1.9.2609.5, debug. Candidate `0d002f1941d1bed0102c19f60ede150f1cfac668` uses merged main `afc5ee86ae3a9521c9f15d96505cd73fe72f2191`.
- `cargo test --offline --locked -j 2 -p xcl --lib gpu::dxil::module::split::tests -- --test-threads=1 --nocapture` reported 10 passed, 0 failed, 0 ignored, and no runtime skips. The open Wave32 fixture reported 256 DWORDs per group and matched the whole shader and CPU reference. Keeping the merged base's allocator and adding only the same CPU fixture check gave the expected negative control of 288 DWORDs. The suite also checked payload readbacks and the current oversized and split-wave cases.
- The same candidate tree ran the open workspace on the RTX 4070 Ti SUPER. After `cargo build --offline --locked --workspace -j 2`, `cargo test --offline --locked --workspace -j 2 --no-fail-fast -- --test-threads=4` completed with 1,265 passed, 0 failed and 46 ignored. The harness additionally printed 27 `SKIPPED` lines: 21 Wave64 paths, three translation refusals, two missing debug-layer paths and one missing heap-window path. Those are included in the counts reported by Cargo. The open workspace used no retail title inputs.
- nnonno91 independently ran the exact public commit on Radeon Graphics and RTX 5090. Each GPU passed all 10 targeted tests with zero skips and matched the whole and split readbacks. [Report](https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7165250326)
- luckyteagirl independently ran the same ten checks without skips on Radeon RX 6800M at the exact public commit. The guest Wave64 fixture used hardware Wave32 halves. [Report](https://github.com/xcl-dev/xcl/pull/2322#issuecomment-7165844270)
- Independent supporting evidence on the previous `f6fa8a9` parent. ettehn applied the published PortBridge patch, reported 47,712 → 20,064 DWORDs per group for one local record with 12 validated pieces and passed eight split tests on an RTX 5070 Ti Laptop. [Independent report](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7162128623)

**Regression run**

The required paired retail `xcl-smoke` blocks are pending for both main and the exact PR head. The PR remains a draft.

**Not tested**

- The paired retail `xcl-smoke` runs and matched GPU execution time, cold driver compilation and scratch measurements for the three workloads from #2126 are pending. The independent 57.9% scratch reduction is from one unnamed report. [Measurement request](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7157104814)

**AI use**

OpenAI Codex (GPT-6 family; the exact serving variant was unavailable) assisted with rebasing, testing, and drafting. The contributor opened the draft on GitHub.
