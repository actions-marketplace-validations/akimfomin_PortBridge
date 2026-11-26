# PortBridge API v1

[Русский](API.md) · [Quick start](docs/QUICKSTART.md)

The local public API starts at `http://127.0.0.1:8765/api/v1`. Requests use `GET` and return UTF-8 JSON. Card IDs such as `PB-0001` remain stable as sources and statuses change.

## Look for prior work

```text
GET /api/v1/preflight?q=rectlist&limit=10
GET /api/v1/preflight?url=https%3A%2F%2Fgithub.com%2Fubiquitarianism%2Fleonida%2Fpull%2F207
GET /api/v1/problems/PB-0001
```

Preflight accepts a description or symbol in `q`, a public GitHub issue, PR, or commit in `url`, or both. An exact PortBridge ID opens its card. `#772` looks for that number across repositories. A confirmed card matches an exact ID or a reviewed source URL. A candidate needs source review.

`first_check` appears when a reviewed test applies to the requested source. Read its revision, platform, outcome and quoted observation before trying the same case in another build. `same_revision` means two sources share a commit. `instruction_variants` points to related instruction families whose exact behavior and test scope still need comparison.

If `indexed` is false, the requested source is absent from the current snapshot. For a tracked repository, use `python -m portbridge sync --source <URL>` to refresh one source in a local catalog. `source_coverage` reports the last refresh and the progress of historical indexing by project.

## Public endpoints

| Path | Parameters | Result |
| --- | --- | --- |
| `/api/v1` | — | Version, metadata and endpoint links |
| `/api/v1/activity` | — | Seven-day progress, per-project counts, source events and shared checks |
| `/api/v1/lab` | `equipment`, `status`, `task` | Public volunteer tasks, revision pins, test requirements and reporting links |
| `/api/v1/projects` | — | Tracked projects, source coverage and update status |
| `/api/v1/ecosystem` | — | Technical areas, scoped capability evidence, review leads and per-source refresh timestamps |
| `/api/v1/problems` | `q`, `project`, `status`, `partial=1`, `limit` | Curated cards |
| `/api/v1/problems/{id}` | — | One card or 404 |
| `/api/v1/matches` | `q`, `limit` | Source pairs, review state and reason |
| `/api/v1/related` | Public GitHub `url`, `limit` | Index coverage and candidates from other projects |
| `/api/v1/observations` | `q`, `project`, `kind`, `limit` | Public observations |
| `/api/v1/preflight` | `q` up to 1000 characters, `url`, `limit` from 1 to 20 | Cards, candidate matches, a scoped first test and coverage |
| `/api/v1/coordination` | — | Reference point and steps for comparing implementations |
| `/api/v1/graph` | — | Projects, cards and reviewed dependencies |
| `/api/v1/source-history` | `url`, `limit` | Recorded changes in source status or revision |
| `/api/v1/recommendations` | `project`, `limit` | Suggested next steps, evidence and decision maker |
| `/api/v1/outreach` | — | Markdown drafts for review and manual posting |
| `/api/v1/health` | — | Snapshot refresh, coverage and warnings |
| `/feed.xml`, `/feed.ru.xml` | — | Public Atom feeds in English and Russian |

Most list endpoints accept a `q` of up to 300 characters and a `limit` from 1 to 200. `kind` accepts `issue`, `pr`, `commit` or `test`. Invalid parameters return 400, unknown paths return 404, and writes to the public API return 405.

Project `sync_status: unavailable` records an observed public access failure. Previous observations and `last_success` remain available. A Test Lab task with `status: blocked` remains readable and cannot trigger an invitation.

### Activity

`as_of` and `window_start` bound the seven-day window in UTC. `refreshed_at` records the last source refresh attempt. Check `health` and each project's sync status and last successful refresh for coverage.

`counts` and `projects[].counts` distinguish actual PR merges (`merged_at`), currently open PRs with recent updates (including drafts), observed status or revision changes, and dated reviewed test outcomes (including failures). One PR may contribute to more than one count. `events` shows up to ten of each event kind. A project's `last_activity` can also point to an event outside that display limit. `opportunities` links to open work where a reviewed test explicitly lists the target in its scope. Follow the source link for the exact revision, platform and result.

`handoffs` lists reviewed PortBridge contributions across all dates. Each item exposes the examined `revision` and links the receiving discussion in `delivered_url`. It can also link an independent reproduction, a formal review, or adoption in `independent_url`, `review_url`, or `adopted_url`. A receiving pull request merged at the recorded head is counted automatically when it appears in the public index. A changed head needs separate reviewed proof. `counts` totals each stage with proof.

## Read the evidence

`GET /api/v1/health` and `data/health.json` use the same collection facts. `refresh_at` records the end of a collection cycle. Each source and channel separates `last_attempt`, `last_success`, `age_state`, confirmed page counts and structured `errors`. A deferred attempt leaves the previous successful time intact. The static response adds `publication.generated_at` and publication age. Local responses have no publication timestamp.

The API root and static manifest include `data_schema_version`. Public readers can select the immutable files from `site.json.snapshots` and the search manifest from `site.json.search_index.manifest`. Former paths still work. The optional MCP health tool and the prior-work summary use the same freshness fields. [Engineering notes](docs/PORTBRIDGE-M1.md)

- A card lists relevant projects, implementations, dependencies and reviewed sources. Built-in editorial records include English text at `translations.en` where available. Identifiers, URLs, outcome codes and original text remain stable. Automatically collected sources retain the contributor's wording.
- An `independent` result comes from a separate tester. `automated_test` is the outcome of a specific automated check. `maintainer_claim` refers to an author report and `source_observation` to inspected code or history. Read `observed` for the result and its limits.
- A link marked `reviewed_same` has a reviewed technical relationship. `reviewed_symptom` has a shared symptom with cause still open. A `suggested` match needs review. Its `basis` describes the signal and its `score` orders candidates.
- Source status and test outcome are separate. `metadata.last_known_head_sha` retains the last known SHA when the current update lacks one. The test report's `revision` remains the version that was actually tested.
- `ok` means the requested pages refreshed. `partial`, `stale`, `error` and `seed-only` show incomplete refresh, cached data, failure without data, or the initial curated catalog. Dates use UTC.

## Share a result

The outreach endpoint returns `drafts` with stable IDs, target and source URLs, `target_status`, `mode` and a Markdown `message` linking to PortBridge. `reference` shares an existing fix and `comparison` suggests comparing behavior across implementations. Review and send the text in the relevant discussion. [Share compatibility evidence](https://github.com/akimfomin/PortBridge/issues/new?template=evidence.yml)

The optional private exchange supports topic subscriptions, discussion and reviewed reports. It uses separate participant keys configured by the instance owner. [Private exchange API](docs/EXCHANGE-API.md)

## Static site and MCP

GitHub Pages exports the same public data under `data/`, including `activity.json`, `projects.json`, `ecosystem.json`, `problems.json`, `observations.json`, `matches.json`, `health.json`, `coordination.json`, `outreach.json`, `graph.json`, `source-history.json` and `recommendations.json`. Agents can filter these files locally. `data/site.json` includes the export timestamp and `data/health.json` the last refresh attempt.

`ecosystem.json` lists reviewed capability entries with an evidence kind, a narrow scope and a primary GitHub link. Repository leads have `state: needs_review`. Their source IDs and references show where the link was found. `counts.lead_repositories` counts deduplicated leads before the display limit of 60. Sources report `pending`, `ok`, `cached` or `failed`, with attempt and success timestamps.

Each active curated case has a standalone page under `cases/`. Built-in cases default to English with separate `.ru.html` pages, and both languages appear in `sitemap.xml`. Retraction removes active pages on the next export and preserves source history in the catalog. The Atom feeds share stable entry IDs across languages.

The public MCP server reads the same snapshot by default. Call `portbridge_activity` with no arguments for the dashboard data. For an existing local database, pass `--db`. [MCP quick start](docs/QUICKSTART.md#connect-codex-or-claude-code)

The volunteer queue is exported as `data/lab.json`. Call `portbridge_lab` to filter by `amd`, `nvidia`, or `cpu`, readiness, or an exact `task` ID. An omitted filter lists all values. A task's `evidence_stage` describes the existing report. `adoption` reflects the receiving project's decision. [Test Lab guide](docs/TEST-LAB.md)

### Public preflight search

The hosted CLI, MCP tool and one-PR action use the partitioned search index announced in `data/site.json`. They read the relevant partitions for an exact source, issue number or technical query. `catalog_index.partial` indicates limited retrieval on broad queries. The local HTTP route continues to search its local database.

An exact reviewed evidence comment can match its card. This establishes the association with that report. Its recorded outcome and test scope still determine how it can be used.

Use `python -m portbridge.preflight --global --q "vulkan scratch buffer"`, or pass `expand_global: true` to `portbridge_preflight`, to send selected technical terms to public GitHub Search. Use public terms with this option. A source-only query can use the exact indexed source title. `external_search` returns candidate URLs and tells you whether the request was available, partial, or unavailable. This option is disabled for the authorized local exchange. [GitHub Search](https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests)

## Historical work with Discovery

Discovery returns `technical_recommendations` separately from broad `matches` and `automatic_matches`. Automatically retrieved links carry `source_found`. Exact URL queries can include a saved result and its `scan_status`. [Evidence states](docs/PORTBRIDGE-M2.1.md#пять-уровней-доказательств)

```http
GET /api/v1/discovery?q=DXGI+adapter+LUID&project=dxvk
```

The local API accepts `q` or `url`, `project`, `kind`, `status`, `platform`, `before`, `after` and a `limit` between 1 and 10. The inclusive YYYY-MM-DD bounds filter the date the source was reviewed. Matches include the source revision, license, evidence behind the ranking and a proposed test. The static export includes the same corpus in `data/discovery.json`. Preflight and MCP return a `discovery` object for matching queries. [Examples](docs/PORTBRIDGE-M2.md)

## Radar and volunteer Lab

Use `GET /api/v1/radar` and `GET /api/v1/lab` for read-only access. The `console` filter represents the console family separately from the host OS. Volunteers and reviewers act in the authorized local exchange. [Lab contract](docs/PORTBRIDGE-M3-LAB.md)

## People and Impact

`GET /api/v1/people` accepts `q`, `profile`, `project`, `specialty`, `console`, `period`, `target`, `after`, and `limit`. Use the returned profile ID or lowercase GitHub handle. `target` is a public GitHub permalink. The response includes profiles, evidence, scoped connections, and a pagination cursor. Observed technical work and voluntary availability are separate fields.

`GET /api/v1/impact` accepts `console`, `kind`, and `target`. Filters narrow the stories. Measures describe the whole snapshot, including their scope and evidence. `null` means unknown. Static files are `data/people.json` and `data/impact.json`. Both views are read-only. [Evidence rules](docs/decisions/016-community-evidence.md)

## Partner feed

Use `GET /api/v1/partner?console=ps5&kind=result&limit=10`, `data/partner.json`, or `portbridge_partner`. Read the current immutable filename from `data/site.json`. Filters are the project slug, `xbox-series` or `ps5`, and `task` or `result`. IDs are stable and result items carry the primary sources. A curated task marked `check_source` needs a status and revision check before taking it.

Embed `partner.html?project=anyps5&kind=task` in an iframe with a descriptive title. For a pull-based subscription run `python -m portbridge.integrations --console ps5 --cursor partner-ps5.json`. Add `--snapshot /path/to/data/partner.json` to read a saved export. A failed pull, snapshot older than 48 hours or rollback in generation leaves the cursor unchanged. A removed item may have been taken, completed, superseded or withdrawn. Follow its source for the reason. [Pilot quick start](docs/PORTBRIDGE-M5-START.md)
