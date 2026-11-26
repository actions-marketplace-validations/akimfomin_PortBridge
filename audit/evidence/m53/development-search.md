# Repeating the three M5.2 technical cases

The candidate returned useful prior work for one of the three known decisions, Continued #2392. All three search requests returned complete first pages. Each run started from the original PR URL and a fresh catalog. Its metadata came from the verified M5.2 input, supplemented by the original PR body's creation timestamp on GitHub. The receipt keeps every raw rank, merge time when supplied, and final result. These are development cases. [Receipt](development-search.json) · [Frozen decisions](../m52/intent.md) · [M5.2 rankings](../m52/assessment.md)

| Origin | M5.2 | Candidate | Decision |
| --- | --- | --- | --- |
| XCL #2852 | 0 useful / 5 | 0 / 5 | The same five sources returned in the same order for `command list`. They concern re-emitting GPU state, a timeout, barrier flushing, a debugger command and a rendering hang. All five retain their original grades. The earlier RenderDoc lifetime example is still a manual find. [Original rank assessments X1–X5](../m52/assessment.md) · [Manual source read](old-xcl-continued.md) |
| Continued #2392 | 0 / 5 | 2 / 5 | Two earlier merged changes in the receiving project supply a device-setting comparison and a test for checker-to-runtime cache reuse. The other three ranks are graded below. |
| KytyPS5 #2565 | 0 / 0, no subject | 0 / 0, completed search | `MAX_CONSOLE_LANGUAGE` produced an empty page of earlier merged PRs. The manual console-language fixture remains outside the automatic results. [Manual evidence](old-kyty.md) |

## Continued ranks for `vk_pipeline_check`

1. **#1891, useful.** The checker enables the transform-feedback extension to match the runtime's feature configuration. The team's accompanying record describes a cache-key effect on RX 7900 XT. Add the enabled extension and features to the producer–consumer comparison for that configuration. PortBridge did not run that hardware check. [Checker](https://github.com/ubiquitarianism/leonida/blob/1bf5eeafd7041db163a6f027ba6145262f70e48a/runtime/test/vk_pipeline_check.cpp#L1147-L1151) · [Runtime](https://github.com/ubiquitarianism/leonida/blob/1bf5eeafd7041db163a6f027ba6145262f70e48a/runtime/shims/d3d12_vulkan_device.cpp#L18061-L18075) · [Reported device observations](https://github.com/ubiquitarianism/leonida/blob/1bf5eeafd7041db163a6f027ba6145262f70e48a/docs/pipeline_check.md#L454-L465)
2. **#821, useful.** A regression test launches the standalone producer, checks the saved bytes against the runtime device, creates the same compute pipeline and checks the valid application-cache-hit bit. If the seed misses, a cache produced by the runtime device itself serves as a positive control. A driver unable to report even the control hit gets a skip. Adapt that comparison to a journal entry written by the present precompiler and read by the playing path. The historical test used the old seed file. [Producer and header](https://github.com/ubiquitarianism/leonida/blob/32a5d9698022711bc52e3c5cf28766691518dc8e/runtime/test/pipeline_cache_seed_test.cpp#L299-L332) · [Creation, feedback and control](https://github.com/ubiquitarianism/leonida/blob/32a5d9698022711bc52e3c5cf28766691518dc8e/runtime/test/pipeline_cache_seed_test.cpp#L363-L417)
3. **#1630, miss.** Its merged tests check stream-output statistics queries. The discussion points to #1891 and other cache work. The query tests add no separate check for the cache decision. [Query test](https://github.com/ubiquitarianism/leonida/blob/5fab9396763ca4d052af8abc71f29ad200e7b5ef/runtime/test/d3d12_vulkan_device_test.cpp#L6813-L6823)
4. **#1796, miss.** The quickstart gives the order of build stages. [Changed instructions](https://github.com/ubiquitarianism/leonida/blob/39c69c2bdc1fc6f443dcd7419cb33b3b6793609b/docs/i18n/ru/quickstart.md#L114-L118)
5. **#43, miss.** The utility checks whether source files are newer than the checker executable. [Timestamp comparison](https://github.com/ubiquitarianism/leonida/blob/091aa263359e5c05d148dd18af35cda6226ee384/tools/stale_build.py#L36-L50)

## Reproduce the three development results offline

From the audit checkout containing this report, create a separate checkout of the published experiment and run the replay. Python and Git are sufficient. [Public candidate revision](https://github.com/akimfomin/PortBridge/commit/10182c8c3bb66c25f67e16a6e49fc3d3e38e485a)

```sh
git worktree add --detach ../m53-candidate 10182c8c3bb66c25f67e16a6e49fc3d3e38e485a
python -B audit/m53_replay_development.py --code ../m53-candidate
```

The replay verifies the recorded SHA-256 fingerprint of the product files. It feeds the three saved normalized observations to the candidate, checks the exact outgoing search URL for each, supplies the archived page, and compares the entire returned result including rank order. Expected final line is `3/3 results matched, 0 HTTP requests.` The original capture also exercised PR-body parsing. That step requires the original body text and precedes this public replay. The link grades above are a manual source review.
