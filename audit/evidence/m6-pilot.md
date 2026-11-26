# M5 external pilot · Continued #2392

On 26 November 2026 at 20:09:31 UTC, PortBridge posted one optional check in the receiving team's open PR. Both public links can be read directly in its existing review. [Pilot handoff](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7202363138) · [PortBridge version offered](https://github.com/akimfomin/PortBridge/commit/0cb1fe46d14f0930e7e347e3c9980a53c9d94be9)

| Who acted | What can be independently checked |
| --- | --- |
| Continued contributor before the pilot | On the RTX 5070 the second precompile stage run skipped a journaled synthetic compute pipeline and preserved the journal bytes and file time. That check preceded our message. The author later rebased to `f445e3f7d5b17ada1d8e1bee66e76dcd2a376515` and reported the stage and crash recovery checks. [Reviewer](https://github.com/ubiquitarianism/leonida/pull/2392#pullrequestreview-6078729866) · [Author's update](https://github.com/ubiquitarianism/leonida/pull/2392#issuecomment-7201637364) |
| PortBridge | The earlier M5.3 experiment retrieved Continued's own #821. Its test checks for valid driver feedback and an application cache hit. When the supplied seed misses, the test reloads a cache produced by the same device, and skips if the driver cannot report even that positive control. We proposed adapting the input to the journal written by this PR and testing its actual consumer on a synthetic pipeline. The test and prior GPU runs belong to Continued. [Test and control](https://github.com/ubiquitarianism/leonida/blob/32a5d9698022711bc52e3c5cf28766691518dc8e/runtime/test/pipeline_cache_seed_test.cpp#L363-L417) · [Archived retrieval](m53/development-search.md) |
| External participant after the handoff | At the 20:10 UTC readback, GitHub showed the one delivered comment. No public response, independent run of this new check, decision, installation or repeat use was recorded. The maintainer can reply in that same thread. |

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

The question was whether the linked control changes a review decision. Only the recipient can establish that outcome. A public reply giving a decision or describing their own check can supply evidence. Any voluntary installation in their repository requires their consent. The public comment and PortBridge's runs are excluded from the usage counters. The historical FrameLab repeat remains one team; at this checkpoint the relaunch has zero verified first uses and zero repeat teams. A search of public references and a check of the existing interactions found no attributable later-version use. Private installations and reads cannot be inferred. [Counting rules](network.md)

We also read the newer test on Continued #2399 before selecting a recipient. The reviewer already probed zero-count placement, checked the following sample mask, compared base against head on an RTX 4090 and ran a nonzero-count control. The team had answered the question previously suggested for a pilot there. [Independent GPU comparison](https://github.com/ubiquitarianism/leonida/pull/2399#issuecomment-7201979513)
