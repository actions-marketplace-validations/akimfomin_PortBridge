# M5.2 Discovery evaluation

Three technical PRs and one documentation control were [selected before tuning](intent.md). The baseline returned no sources on any of them. M5.2 searched for prior work on two technical PRs and returned ten sources. None satisfied the predeclared decisions. The third technical PR still had no subject; the documentation control correctly abstained in both versions. Four convenience-sampled PRs cannot establish a population success rate.

## Prospective results

The input was the linked PR alone. Each arm received the same title and complete body. Each row gives the extracted search subject, the number of external **search** lookups issued by each release, and the final rank list. Every issued query was captured from GitHub once. The final run reused those responses, with zero new HTTP requests. The five sources in either nonempty list appear below in their returned order. Empty means an actual empty list. The developer decisions are the auditor's assessment, with no claim of an author response.

| PR | M5.1 subject / requests / top five | M5.2 subject / requests / top five | Decision supported |
| --- | --- | --- | --- |
| [XCL #2852](https://github.com/xcl-dev/xcl/pull/2852) | None / 0 / empty | `command list` / 1 / X1-X5 | Keep the final-release question open. No source shows how to clear pointer-keyed state before an address is reused. Test immediate address reuse with distinguishable tracking for the old and new objects. |
| [Continued #2392](https://github.com/ubiquitarianism/leonida/pull/2392) | None / 0 / empty | `vk_shader_stage_all` / 1 / C1-C5 | Retain the runtime cache-key check. None of the returned sources compares a precompiler's cache entries with the corresponding runtime entries. |
| [KytyPS5 #2565](https://github.com/KytyPS5/KytyPS5/pull/2565) | None / 0 / empty | None / 0 / empty | Unresolved. Discovery supplied no independent source for a console language ID 30 -> uk-UA fixture. |
| [AnyPS5 #27600](https://github.com/boykopovar/AnyPS5/pull/27600), negative control | None / 0 / empty | None / 0 / empty | Keep review focused on the repository's documented manifest. No unrelated external recommendation was made. |

| Rank | Original source | What the source addresses |
| --- | --- | --- |
| X1 | [vkd3d-proton #3399](https://github.com/HansKristian-Work/vkd3d-proton/pull/3399) | Restores pipeline and descriptor state after an embedded GPU launch within a live command list. |
| X2 | [vkd3d-proton #3525](https://github.com/HansKristian-Work/vkd3d-proton/issues/3525) | Reports a rendering timeout with no framebuffer attachments on a tiled GPU. |
| X3 | [vkd3d-proton #3355](https://github.com/HansKristian-Work/vkd3d-proton/issues/3355) | Moves a command flush before a copy-barrier fast path. |
| X4 | [LLVM #239954](https://github.com/llvm/llvm-project/pull/239954) | Changes the debugger command that lists processes. |
| X5 | [vkd3d-proton #3508](https://github.com/HansKristian-Work/vkd3d-proton/issues/3508) | Reports a GPU hang during streaming and command-list diagnostics. |
| C1 | [Vulkan-ValidationLayers #13524](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/13524) | Discusses error recording for fragment-shader helper invocations. |
| C2 | [MoltenVK #2573](https://github.com/KhronosGroup/MoltenVK/issues/2573) | Concerns layout-support queries for bindless descriptors and update-after-bind. |
| C3 | [Vulkan-ValidationLayers #13419](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/13419) | Tests debug output with descriptor buffers and ordinary descriptor sets. |
| C4 | [Vulkan-ValidationLayers #10549](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/10549) | Describes validation of image and memory lifetimes. |
| C5 | [Vulkan-ValidationLayers #13596](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/13596) | Reports a descriptor-allocation validation issue. |

All ten ranks came from GitHub's bounded first page. The baseline's separate URL-only reviewed index channel was also empty for all four cases. Both searched pages reported complete results. The ten source descriptions were opened to assess applicability. Reading a source for this review is separate from the product's search count. No patches or attachments were executed.

## Known regression, outside the four

[AnyXboxX #429](https://github.com/LooperSalty/AnyXboxX/pull/429) was already merged at the [frozen head](known-regression.json) `0d20059eeeb6de1dd22c84ef14a1a8f39b5f2627`. [M5.1's historical receipt](../discovery.md) used an earlier open head, an additional user-written query and a separate automatic scan.

At the new frozen head, M5.1's subject was empty, its ordinary scan selected zero origins and both rank channels were empty. Its scheduled scan also excludes merged PRs. The final M5.2 explicit URL path extracted `updatetilemappings`, issued one search lookup and automatically returned the five sources below in order. Ordinary batch monitoring still excludes merged PRs.

During development the first M5.2 implementation selected `d3d12_tile_range_flag_null` and returned an available, complete, empty page. A separate manually selected `updatetilemappings` query was then made against the same endpoint and scope. This motivated prioritizing an operation over an argument enum when both are present. The final automatic search on the known case reproduced the manually discovered page. This case therefore demonstrates a regression fix; it is outside the independent success count. The four already frozen prospective cases retained the same subjects, rank lists and grades. [First run](development-run.json)  /  [Manual diagnostic receipt](known-diagnostic.json)

### Known-case final top five

1. [vkd3d-proton #3425](https://github.com/HansKristian-Work/vkd3d-proton/issues/3425) reports memory consumption from eagerly backing an entire reserved resource on hardware without sparse support.
2. [vkd3d-proton #3231](https://github.com/HansKristian-Work/vkd3d-proton/pull/3231) changes address alignment for placed resources.
3. [vkd3d-proton #2307](https://github.com/HansKristian-Work/vkd3d-proton/pull/2307) supplies a reusable starting point for a test. A reserved buffer is repeatedly unbound and remapped on one queue. The test reads back which tile supplied each value and checks zero for unmapped pages. The implementation flushes overlapping tile updates on a single resource. To test the receiving allocator's decision, extend the check to two textures reusing a physical tile with earlier work deliberately outstanding. The existing test uses a buffer and reads back between iterations. A cross-queue release fence for the receiving textures remains unverified. [Pinned stress test](https://github.com/HansKristian-Work/vkd3d-proton/blob/d912baf6d70254b105036ba718bafaec3cdd7a35/tests/d3d12_sparse.c#L420-L497)  /  [Pinned overlap handling](https://github.com/HansKristian-Work/vkd3d-proton/blob/d912baf6d70254b105036ba718bafaec3cdd7a35/libs/vkd3d/command.c#L19158-L19176)
4. [vkd3d-proton #2194](https://github.com/HansKristian-Work/vkd3d-proton/pull/2194) checks the range of page-table updates. It does not establish completion of older work.
5. [vkd3d-proton #1176](https://github.com/HansKristian-Work/vkd3d-proton/pull/1176) discusses copy-queue tile updates and changes fence-wait submission. The author explicitly leaves ordering across all queues uncertain.

Rank 3 supplies a focused test design that a developer could adapt. No test was run on the receiving allocator and no source resolved cross-queue fence safety.

## Reproduce

[Baseline output](baseline.json) and [candidate output](candidate.json) retain allowed normalized fields, the SHA-256 fingerprint of product files and the actual results. [Search replies](search-responses.json) preserve query, page order, timestamps, failure or partial state and the public fields consumed in ranking. [Baseline transport](baseline-transport.json) and [candidate transport](candidate-transport.json) record search requests and fixture reads separately.

The original metadata capture read each of the four prospective PRs and the known PR from GitHub. These five input reads were shared across releases. M5.1 consumed each frozen input through its production parser and batch scan, followed by URL-only Discovery. M5.2 called its public link function with one cached origin reply per PR. Across development and final scoring, GitHub received four distinct search HTTP requests with zero retries: two on novel inputs, one for the initial known-case enum, and one for its manually chosen operation. The final algorithm issued three search lookups, all fulfilled by exactly matching frozen pages. Its actual network count was zero. A subsequent verification also exercised its URL function and parser using five new public metadata reads and the same archived search replies. Repository listing, input verification and the auditor's visits to assess candidates are outside those counts.

From the candidate checkout, select the previous public release in a separate checkout and run the archived evaluations. Both replay commands use only recorded responses and fresh temporary catalogs.

```sh
git worktree add --detach ../portbridge-m51-baseline 0738093add1ed01dad89c4bdcb6df74eb8891701
python -B audit/m52_replay.py --arm baseline --code ../portbridge-m51-baseline
python -B audit/m52_replay.py --arm candidate
```

The offline mode starts at the archived normalized observation. To also exercise parsing and the candidate URL entry, add `--public-inputs`. This performs five public metadata reads, verifies the original PR title, head and complete body's SHA-256, and restores its frozen labels, status and timestamp. It still replays the recorded search pages. If an editable title or body or target head changes, use the offline mode. The candidate's five-input public verification passed. A later optional baseline public recheck hit GitHub's anonymous rate limit. Its full frozen-input replay passed. The production command itself queries current sources and may return a different order later.

```sh
python -B -m portbridge.discovery_scan --url https://github.com/xcl-dev/xcl/pull/2852 --online
```
