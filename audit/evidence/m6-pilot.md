# M5 external pilot · Continued #2392

On 26 November 2026 at 20:09:31 UTC, PortBridge posted one optional check in the receiving team's open PR. Both public links can be read directly in its existing review. [Pilot handoff](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202363138) · [PortBridge version offered](https://github.com/akimfomin/PortBridge/commit/0cb1fe46d14f0930e7e347e3c9980a53c9d94be9)

| Who acted | What can be independently checked |
| --- | --- |
| Continued contributor before the pilot | On the RTX 5070 the second precompile stage run skipped a journaled synthetic compute pipeline and preserved the journal bytes and file time. That check preceded our message. The author later rebased to `f445e3f7d5b17ada1d8e1bee66e76dcd2a376515` and reported the stage and crash recovery checks. [Reviewer](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6078729866) · [Author's update](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7201637364) |
| PortBridge | The earlier M5.3 experiment retrieved Continued's own #821. Its test checks for valid driver feedback and an application cache hit. When the supplied seed misses, the test reloads a cache produced by the same device, and skips if the driver cannot report even that positive control. We proposed adapting the input to the journal written by this PR and testing its actual consumer on a synthetic pipeline. The test and prior GPU runs belong to Continued. [Test and control](https://github.com/ubiquitarianism/leonida/blob/32a5d9698022711bc52e3c5cf28766691518dc8e/runtime/test/pipeline_cache_seed_test.cpp#L363-L417) · [Archived retrieval](m53/development-search.md) |
| qhukz13, 20:37:55 UTC | The contributor welcomed the suggested control and chose Continued's own #2198 diagnostic. On Windows 10, MSVC, GTX 1050 Ti and NVIDIA 582.66, one process warmed a journal and a fresh process required a driver-reported application cache hit. It passed. This run establishes the known positive control. [Reply and result](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202911853) |
| lixonik, 20:43:03 UTC | On Windows 11, MSVC, RTX 5070 and NVIDIA 610.88, the reviewer used one synthetic compute module for three trials. The empty journal produced `missing_or_unusable=1`. The diagnostic's own journal and the actual #2392 stage output each produced `verified=1` in a separate process requiring the driver hit bit. Both populated files remained unchanged. The reviewer also reran the stage twice and reported 26 passes and one skip in its two targeted Python files. [Commented review](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6080300502) |

The receiving team could now distinguish a usable driver cache entry from an unchanged journal file and had evidence for that claim on the tested #2392 compute pipeline. Both contributors disclosed AI assistance. The authorship of the diagnostic, stage and hardware runs belongs to Continued. At readback both PRs were open and unmerged. [Stage head f445e3f7d5b17ada1d8e1bee66e76dcd2a376515](https://github.com/ubiquitarianism/leonida/pull/2392) · [Diagnostic at 95267b8c7bba786e356bef364dc25862a26ebab8](https://github.com/ubiquitarianism/leonida/blob/95267b8c7bba786e356bef364dc25862a26ebab8/scripts/check_precompile_verify.py) · [Diagnostic PR](https://github.com/ubiquitarianism/leonida/pull/2198)

### Reproduce the maintainer-side check

Each of the two clean checkouts was given the same ordinary PR URL and a fresh catalog. At 20:07 UTC both selected the crash code `0xc0000005` from the updated description, made one anonymous search request and returned the same five sources. All five were unrelated to verifying a journal hit. The handoff linked the earlier saved useful source directly and disclosed the regression in applicability. This observation leaves the M5.3 decision to stop tuning Discovery in place.

```sh
git worktree add --detach ../pb-pilot-default 0cb1fe46d14f0930e7e347e3c9980a53c9d94be9
git worktree add --detach ../pb-pilot-experiment 10182c8c3bb66c25f67e16a6e49fc3d3e38e485a
# Run from each new worktree with its own fresh database:
python -B -m portbridge.discovery_scan --db .portbridge/continued-pilot.sqlite3 --online --url https://github.com/ubiquitarianism/leonida/pull/2392
```

GitHub search and PR text can change. The live results at the time, in rank order, were [vkd3d-proton #3512](https://github.com/HansKristian-Work/vkd3d-proton/issues/3512), [AnyPS5 #26751](https://github.com/boykopovar/AnyPS5/pull/26751), [LLVM #240354](https://github.com/llvm/llvm-project/issues/240354), [AnyPS5 #25661](https://github.com/boykopovar/AnyPS5/pull/25661) and [KytyPS5 #1859](https://github.com/KytyPS5/KytyPS5/issues/1859). The fresh-checkout command reproduces the method. The [M5.3 archive](m53/development-search.json) preserves the earlier head for deterministic replay.

### Participation and follow-up

At the first 20:10 UTC readback, the invitation alone counted for zero. The two later public reports establish that one external team applied a PortBridge recommendation on one task. The revision link appears in the offer. Neither participant reported running or installing PortBridge. There is no measured time saving, second task or independent M5 software-use receipt. Historical FrameLab repeat use remains one team. The network CLI exposes the applied recommendation under `outcome.relaunch.advisory_handoffs`. [Counting rules](network.md)

We also read the newer test on Continued #2399 before selecting a recipient. The reviewer already probed zero-count placement, checked the following sample mask, compared base against head on an RTX 4090 and ran a nonzero-count control. The team had answered the question previously suggested for a pilot there. [Independent GPU comparison](https://github.com/ubiquitarianism/leonida/pull/2399#issuecomment-7201979513)
