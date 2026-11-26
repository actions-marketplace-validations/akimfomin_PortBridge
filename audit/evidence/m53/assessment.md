# Prospective URL-only Discovery assessment

The [preregistered procedure](protocol.md) preceded listing inspection, and the [five PRs](inputs.json) and [decision criteria](intent.md) were frozen before running either version. The PRs come from five previously assessed projects with one fresh origin per project. This convenience sample supports case-level observations. Earlier chosen development examples are outside this score.

## Result across five previously unseen PRs

The public [M5.2 release](https://github.com/akimfomin/PortBridge/commit/df8cfd879c17df04644127c35330ef07407e9392) and [frozen M5.3 candidate](https://github.com/akimfomin/PortBridge/commit/10182c8c3bb66c25f67e16a6e49fc3d3e38e485a) match the tested Git trees. The local [selection protocol](https://github.com/akimfomin/PortBridge/blob/789bc3f8e923690084f91637dda09698949c6e7e/audit/evidence/m53/protocol.md) was committed at 19:29:02 UTC, the [questions and input pins](https://github.com/akimfomin/PortBridge/blob/d602323b17cb051cf6e8318a5c8bc320b6cd77fc/audit/evidence/m53/intent.md) at 19:31:17 UTC and the candidate at 19:41:46 UTC. The baseline capture ran at 19:32:35–37 UTC. An independent evaluator captured the candidate results at 19:42:38–40 UTC after checking all five public heads and complete text hashes. The implementer saw the holdout only after the candidate freeze. The local Git trees and their publication equivalents are recorded in [validation.json](validation.json). [Origin checks](origin-verification.json) / [replay instructions](replay.md)

| Observed measure | M5.2 | M5.3 |
| --- | ---: | ---: |
| PRs with a novel source that meets the predeclared technical decision | 0/5 | 0/5 |
| Confirmed author-supplied references that answer the decision | 0 | 0 |
| Already-cited historical references retrieved, below the decision threshold | 0 | 1 |
| Other adjacent but insufficient ranks | 1 | 3 |
| Off-topic ranks | 4 | 7 |
| Total decision-inapplicable ranks / total displayed | 5/5 | 11/11 |
| PRs with an empty top five | 4/5 | 2/5 |
| PRs on which the system abstained before a search | 2/5 | 0/5 |
| Logical search requests / distinct new search HTTP attempts | 3/3 | 5/4 |
| Partial, unavailable or failed search pages | 0 | 0 |

Seven distinct bounded search pages were requested over both arms. AnyXboxX used the same exact URL and frozen reply in both. Each URL entry used the same captured PR input in both arms. Four candidate cases moved to receiver history, which found eleven links but answered none of their four questions. A search keyword derived from the author's text does not count as a rediscovered author-provided source. No case produced a previously unmentioned source that established a new assumption or test for the frozen decision.

| Origin | M5.2 subject, ranks | M5.3 subject, ranks | Source-supported reading |
| --- | --- | --- | --- |
| XCL #2860 | abstain, 0 | `XCL_DEVICE_TYPE`, 2 | The sources explain profile selection, including aliases, and how settings reach other subsystems. Neither checks cross-profile usage manifests. The origin already tests the older profile aliases, file names and worker environment values. |
| Continued #2399 | `d3d12_pipeline_state_subobject_type_view_instancing`, 0 | `VIEW_INSTANCING`, 0 | External search and earlier receiver PR search returned empty pages. The Microsoft stream layout was found manually. The author linked a coordination issue, absent from both ranking lists. |
| KytyPS5 #2551 | `device loss`, 5 | `shader_recompiler_compute_tests`, 5 | The candidate selected a test-binary name from verification prose. All five results are unrelated to the image destruction/retry condition. The baseline had one adjacent error-path test. |
| AnyPS5 #27618 | abstain, 0 | `mmap_np`, 4 | Rank 1 recovers the already-named upstream implementation, which explicitly left the target path unimplemented. The other ranks do not establish preservation of errno across a diagnostic. The specific author-linked issue comment was not returned. |
| AnyXboxX #448 | `dxgi_error_device_suspended`, 0 | same subject and page, 0 | A failure string led to an empty page in both arms. LLVM's floating predicate rules were located by manual reading. |

The reviewer independently found external sources informing at least one part of each of the five fixed decisions. The manual search in each receiver also found earlier implementation context for two of the five. These are separate, manually constructed queries. None of the manual sources was returned as a qualifying product result. No outside maintainer decision, adoption, hardware result, saved developer time or general improvement is measured. [Manual checks and limitations](manual.md)

## Baseline rank review

Only KytyPS5 #2551 had any ranks in M5.2. None of its first five sources establishes the image-retirement rule required by the fixed question. The first one is adjacent technical evidence and is identified explicitly below. The other four do not address the decision.

| Rank | Source | Observation |
| --- | --- | --- |
| 1 | [Continued #1298](https://github.com/ubiquitarianism/leonida/pull/1298) | Tests the error branch when a Vulkan retire-ticket query first reports device loss. The test expects a zero completed ticket. It does not exercise destruction of an idle image, the last use via an image view, or the allocation-pressure retry. This is related failure-handling evidence below the predefined applicability threshold. |
| 2 | [Vulkan-ValidationLayers #13704](https://github.com/KhronosGroup/Vulkan-ValidationLayers/issues/13704) | A validation-assisted vertex-attrib check on a generated-command draw causes device loss. No backing-retirement condition. |
| 3 | [wgpu #11123](https://github.com/gfx-rs/wgpu/pull/11123) | Changes the order of command-buffer checks and deferred query resolution on submit. No image eviction or final-use check. |
| 4 | [Continued #1909](https://github.com/ubiquitarianism/leonida/pull/1909) | Labels compute pipelines to aid crash diagnosis. No image release rule. |
| 5 | [Continued #1931](https://github.com/ubiquitarianism/leonida/pull/1931) | Adds file-read tracing for boot diagnosis. No image release rule. |

Bodies of the above public issues/PRs were read from the full search responses. Public receipts keep each title, URL, state, creation/update time, PR merge timestamp where available, and the order returned by GitHub. A raw third-party body or account is unnecessary for offline product ranking. A frozen empty page is distinct from a release abstaining before a lookup.

## Candidate rank review

Every candidate rank came from the selected repository and had a public merge time before the origin's recorded creation time. All eleven PR descriptions were inspected. Specific code links below document the close calls. Results appear in GitHub order within each case. The other two candidate PRs produced no ranked links. [Exact candidate output](candidate.json) / [captured transport](candidate-transport.json)

| PR and rank | Returned source | Assessment against the frozen question |
| --- | --- | --- |
| XCL 1 | [XCL #1053](https://github.com/xcl-dev/xcl/pull/1053) | Adjacent. Introduces a profile override and tests its resolution. The checked behaviors concern profile settings and memory, not profile-specific usage-manifest or precompile-worker isolation. |
| XCL 2 | [XCL #2311](https://github.com/xcl-dev/xcl/pull/2311) | Adjacent. Demonstrates configuration aliases that previously selected the wrong console memory size. The new origin already uses this parser and tests the same alias family along with worker forwarding. The returned source does not add a profile-switch manifest check. [Earlier alias test](https://github.com/xcl-dev/xcl/blob/d2515bc8c5c2b71149aa836513449bc4e2117cd1/crates/xcl/src/config.rs#L358) / [frozen origin assertions](https://github.com/xcl-dev/xcl/blob/6efa82fab8dce5df52e7f69fff5539b8258e2d2c/crates/xcl/src/hle/d3d12x/pso_async.rs#L2402-L2421) / [worker assertion](https://github.com/xcl-dev/xcl/blob/6efa82fab8dce5df52e7f69fff5539b8258e2d2c/crates/xcl/src/shaders.rs#L2696-L2705) |
| KytyPS5 1 | [KytyPS5 #1983](https://github.com/KytyPS5/KytyPS5/pull/1983) | Off topic. Removes a collision with a Windows macro in a test build. |
| KytyPS5 2 | [KytyPS5 #1893](https://github.com/KytyPS5/KytyPS5/pull/1893) | Off topic. Decodes packed color clears. |
| KytyPS5 3 | [KytyPS5 #801](https://github.com/KytyPS5/KytyPS5/pull/801) | Off topic. Preserves shader lane predicates through whole-quad expansion. |
| KytyPS5 4 | [KytyPS5 #2528](https://github.com/KytyPS5/KytyPS5/pull/2528) | Off topic. Tests median instruction handling for NaN and signed zero. |
| KytyPS5 5 | [KytyPS5 #1924](https://github.com/KytyPS5/KytyPS5/pull/1924) | Off topic. Decodes high-half shader loads. |
| AnyPS5 1 | [AnyPS5 #22709](https://github.com/boykopovar/AnyPS5/pull/22709) | Already named in the origin. The older PR saves and restores errno around guest memory copies. In the specific mapping failure branch, it still throws an unimplemented exception. The origin also cites [an earlier public observation](https://github.com/boykopovar/AnyPS5/issues/21870#issuecomment-6942781835) with the diagnostic arguments and return value. Discovery did not retrieve that comment. To test the remaining host guarantee, deliberately change errno inside the diagnostic and check for MAP_FAILED plus ENOMEM. [Earlier copy wrapper](https://github.com/boykopovar/AnyPS5/blob/7e9e108d0fde2d299eca74e9fec166687c541264/core/libs/prx/libScePosixForWebKit/Export.cpp#L52-L74) / [original mmap branch](https://github.com/boykopovar/AnyPS5/blob/7e9e108d0fde2d299eca74e9fec166687c541264/core/libs/prx/libScePosixForWebKit/Export.cpp#L391-L400) / [receiving test](https://github.com/boykopovar/AnyPS5/blob/e05d132a8dbc56e3e436f3d6f152bf23164dc68c/core/libs/tests/GuestPosixWrap.cpp#L164-L181) |
| AnyPS5 2 | [AnyPS5 #19430](https://github.com/boykopovar/AnyPS5/pull/19430) | Off topic. Implements clock and environment lookups while mmap remains a stub. |
| AnyPS5 3 | [AnyPS5 #8431](https://github.com/boykopovar/AnyPS5/pull/8431) | Off topic. Declares missing exports as stubs. |
| AnyPS5 4 | [AnyPS5 #9325](https://github.com/boykopovar/AnyPS5/pull/9325) | Adjacent. Its direct mapping wrapper forwards to another routine, with no intervening diagnostic. Its mmap error example exercises EINVAL, and its tests do not check recovery of ENOMEM after a helper changed errno. [Forwarding code](https://github.com/boykopovar/AnyPS5/blob/b9e5dc160f148ddd5724b6c055e5c129c152ba2f/core/libs/prx/libScePosixForWebKit/Export.cpp#L224) |
