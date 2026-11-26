# M5.1 Discovery holdout and pilot reporting

The first open AnyXboxX pull request in the live list was [#429](https://github.com/LooperSalty/AnyXboxX/pull/429), a change that recycles heap tiles from unused standard mips. The [intent](discovery-intent.md) records the exact question and acceptance criterion at 18:32:13 UTC on 26 November 2026. Its SHA-256 when recorded was `481771e22f06cfa7b94a15c65ae8de4fe745f3d02d836542cb64f1c0c3ee3893` (UTF-8, LF). The PR had no pre-mapped case in Discovery. The query and target stayed fixed.

| Route | Actual top five | Assessment against the predeclared criterion |
| --- | --- | --- |
| Ranked Discovery with the PR URL and technical text | Rank 1, [wgpu #10155](https://github.com/gfx-rs/wgpu/pull/10155), score 9. Ranks 2–5 empty. | 0 qualifying hits. wgpu describes retiring a submission before reusing a ray-tracing scratch buffer. The source provides no test or ordering rule for a tiled-texture unmap, remap and tile reuse. The analogy can motivate a test that keeps the old submission in flight while reassigning a tile, but cannot establish that #429 needs a change or that it is safe. |
| Incremental automatic Discovery on the real PR metadata in a fresh catalog | Empty. The scanner extracted no search subject, so **zero external lookups** ran. | No comparison was found by this route. No rate-limit or network error was reported. The single PR's metadata was read successfully. |

The [captured output](discovery-result.json) preserves actual list order, score, source revision, checked-in index fingerprint and automatic-scan status. The one-case check is a negative result for the predeclared question. No author received a recommendation and no use by the author has been observed. The tested mechanism and inputs are public; no game assets were used.

## Reproduce from the repository root

```sh
python -B -m portbridge.discovery_search --url https://github.com/LooperSalty/AnyXboxX/pull/429 --q "D3D12_TILE_RANGE_FLAG_NULL UpdateTileMappings reclaim unmapped mip tiles before heap reuse fence completion" --limit 5
python -B audit/replay_discovery.py
python -B audit/replay_discovery.py --online
```

The first two commands use the versioned ranking data. The last command also retrieves the current PR and uses the production normalizer, scanner and result reader with a temporary database. Live PR metadata or GitHub results may change. Compare the PR head and scan state before comparing rankings.

## Historical M5 Lab replay

The [three recorded M5 rank lists](historical-m5-pairs.json) came from the M5 online receipt. All three Lab pairs were selected manually. None came back in its own automatic top five. Independent FrameLab use predates M5. The three scripted M5 cases used two local clients, with zero verified independent deployments of M5 by other teams. [Historical FrameLab use](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587)

The [pilot](../agent_pilot.py) now detects the OS at report generation and places it in the report submitted for review. The public inputs contain four project PRs and six pinned source receipts. A repeat on the actual Windows host reproduced the three scoped source comparisons (Kyty PASS, Continued FAIL, XCL FAIL), identical to the historical outcomes. A regression replaces the OS detector with Linux and Windows in separate runs and verifies the environment in each of the six report payloads. Only Windows was physically exercised here. No GPU work or real volunteer is part of this replay.

```sh
python -B audit/verify_pilot_sources.py
python -B audit/agent_pilot.py .portbridge/m51-pilot-replay
python -B -m unittest discover -s tests -p test_pilot_platform.py -v
```

The first command verifies the bytes and anchors of six source files online. The second uses the archived receipts and two local MCP clients offline. Give it a fresh directory each time. Detailed pilot output and its temporary credentials database belong in the ignored local workspace. The regression uses automatically removed temporary directories. Public source URLs and test outcomes are sufficient for this audit.
