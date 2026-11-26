# Public Lab evidence across five views

Two already published FrameLab hardware reports reproduced the E2E-03 gap. M5.3 Lab marked the task complete while Search and Radar read only the separate local Radar reports table. The previous curated Impact article mentioned the historical use independently.

At 20:22 UTC on November 26, 2026, anonymous GET requests to the two configured FrameLab discussions returned both public tester reports, both owner approvals and the original SHA-256 hashes of the reviewed report bodies. The test revision was `82f069e82197e61b97f60bbcbcb7a3af7d3f8e77`. A later anonymous request reached GitHub's shared rate limit. The browser rehearsal used the normalized public receipts from the successful fetch.

| Hardware | Submitted by | Separate approval by |
| --- | --- | --- |
| AMD Radeon 860M | [JoeY54 · result](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7147944059) | [5headsmartbtw · review](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160150401) |
| AMD Radeon Graphics (Ryzen 9 9950X3D) | [JoeY54 · result](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7153817545) | [5headsmartbtw · review](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160151831) |

Both tester submissions declared `Opt-in: no` or used the equivalent historical format. Permission to send future proposals remains absent. These are historical tests. No new physical run or independent use of M5/M6 by FrameLab took place during the rehearsal.

| View | Result in the isolated export |
| --- | --- |
| Search for the [upstream PR](https://github.com/5headsmartbtw/leonida-framelab/pull/12) | Both report IDs in MCP preflight, with links to the report and approval rendered in the browser |
| Research Radar | Both links for each result rendered on the activity page |
| Lab | Task completed and both results and approvals rendered |
| People | Tester's profile linked each report, repository owner's profile linked each approval |
| Impact | Each reviewed result retained its own attribution and evidence. Delivery, replication and adoption require separate receipts |

The captures contain normalized public report fields, author and reviewer identity, revision and source hashes. Replaying twice returned exactly two distinct reviewed receipts. An isolated fixture using the same importer verified approval, repeat, then revocation across all five projections. After revocation the tester's source remained, the active review disappeared and the delivery, adoption and replication counters stayed unchanged. An owner approving their own report under a different login did not generate an independently reviewed finding. A temporary source outage retains the last verified review with its check time. An authoritative source removal stops publication.

For E2E-04 an isolated pair of PRs with different aliases for one account produced a developer role, a multi-project role and two source-backed suggestions. Correcting one source reassigned it to the verified account and removed the original multi-project claim. Opting out removed that profile and its suggestion. Duplicate decisions made no additional changes. Neither source links nor suggestions granted contact permission, and the test sent no messages. This establishes software behavior on test records. A real person's display correction or withdrawal was not solicited or carried out.

An independent review also supplied the four actual public PR responses from the [intake rehearsal](e2e-intake.md). Before ingest, the isolated catalog had zero matching profiles or suggestions. The normalizer and catalog import found one developer, Vladimir-Human, contributing to both repositories. People linked the two projects, and the local partner selector returned the two open memory-management PRs below with `contact_permission=not_granted`. A simulated display opt-out in that isolated catalog removed the profile and both suggestions. The account owner's real settings remained untouched. To repeat with fresh records, run the intake rehearsal in its live mode and inspect `people(c)[0]["profiles"]` and `opportunities(c)["opportunities"]` for the public account ID `github-user:39053957` immediately after `record_sync`. Changes to the two PRs can change which suggestions qualify. [AnyXboxX #350](https://github.com/LooperSalty/AnyXboxX/pull/350) · [victory-fork #1286](https://github.com/fxceless/victory-fork/pull/1286).

Further negative controls came from independent review. When complete equipment, OS, driver, toolchain, revisions and an observed case match but two active reports disagree, both remain visible for review and neither feeds Impact or partner subscriptions. This also applies to two submissions by the same tester. A different driver is a separate configuration. Simulating a later owner revocation against one of the actual FrameLab receipts removed that source from active partner proofs and reduced the independent-reproduction metric by one. The documentation receipt and verified integration use remained, and the older report was visible as revoked history in Impact. Simulating a complete public thread scan with the source removed produced the same drop. An empty database, temporary outage or partial scan left the prior result in place. Restoring the evidence on a later complete read restored its proof. The real public sources remained untouched.

```sh
python -B audit/m6_framelab_views.py
python -B audit/m6_framelab_views.py --browser /path/to/chromium
python -B audit/m6_framelab_views.py --live
python -B -m unittest discover -s tests -p test_lab_reports.py
python -B -m unittest discover -s tests -p test_community.py
```

The browser read all six rendered routes of the local public-format export, including both People profiles. The default replay requires no GitHub request. `--live` refreshes the two public source threads twice and reports an error on missing or changed evidence or source outage. [Captured receipts](../../fixtures/m6-framelab-receipts.json) · [Runner](../../m6_framelab_views.py) · [Review lifecycle regression](../../../tests/test_lab_reports.py) · [People visibility regression](../../../tests/test_community.py).
