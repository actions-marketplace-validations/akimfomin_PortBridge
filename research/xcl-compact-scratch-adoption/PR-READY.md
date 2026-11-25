# Recompiler: reuse scratch slots across disjoint payload lifetimes

Part of #1269. This follows #2126, which is merged. Keep Kalmarv's persistent scratch payload and lazy restores and reuse a slot once the last destination carrying its previous value has finished. Keep the original fixed offsets when reuse does not reduce stride.

[Fork candidate](https://github.com/akimfomin/xcl/tree/codex/compact-scratch-afc5ee8) at `b3f7ab5574c4489761141e2de0ce31d2eb216412` has the exact Git tree tested below.

**What is in it**

- `crates/xcl/src/gpu/dxil/module/split.rs` adds the PortBridge lifetime allocator, checks the inclusive last-consumer boundary, and makes the existing Wave32 fixture assert actual compaction. The merged oversized-loop variants keep their GPU readback checks.
- `THIRD_PARTY.md` records the origin and GPL-2.0-only license of the PortBridge patch. [Published PortBridge candidate](https://github.com/akimfomin/PortBridge/tree/89884212b8a5718f44b16b66e8df0cf5f263306b/research/xcl-2126-stacked-candidate)

**Tested**

- Windows 11 Pro build 28000, Intel Core i5-13600KF, RTX 4070 Ti SUPER driver 617.14, Rust 1.100.0 gnullvm, DXC/DXIL 1.9.2609.5, debug. Candidate `0d002f1941d1bed0102c19f60ede150f1cfac668` uses merged main `afc5ee86ae3a9521c9f15d96505cd73fe72f2191`.
- `cargo test --offline --locked -j 2 -p xcl --lib gpu::dxil::module::split::tests -- --test-threads=1 --nocapture` reported 10 passed, 0 failed, 0 ignored, and no runtime skips. The open Wave32 fixture reported 256 DWORDs per group and matched the whole shader and CPU reference. Keeping the merged base's allocator and adding only the same CPU fixture check gave the expected negative control of 288 DWORDs. The suite also checked payload readbacks and the current oversized and split-wave cases.
- Independent supporting evidence on the previous `f6fa8a9` parent. ettehn applied the published PortBridge patch, reported 47,712 → 20,064 DWORDs per group for one local record with 12 validated pieces and passed eight split tests on an RTX 5070 Ti Laptop. [Independent report](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7162128623)

**Regression run**

The two XCL smoke blocks are pending. This draft is a handoff for a human contributor and should be submitted according to XCL's regression requirements.

**Not tested**

- Full workspace suite, paired `xcl-smoke` runs, and GPU execution time or cold driver compilation for the three workloads from #2126. Their scratch measurements on the rebased candidate are also pending. The independent report names a single local record and supplies no GPU timing for that record. [Measurement request](https://github.com/xcl-dev/xcl/pull/2126#issuecomment-7157104814)

**AI use**

OpenAI Codex, based on GPT-6, adapted the published patch to merged main, ran the stated commands and drafted this handoff. The session did not expose an exact serving variant. The human contributor reviews the diff and records model/tool details for their own review before opening the PR.
