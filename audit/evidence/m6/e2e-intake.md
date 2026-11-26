# E2E-01 and E2E-02 · intake evidence

## Four public PRs, two questions

On 26 November 2026 at 20:23 UTC a clean PortBridge catalog ingested the four live GitHub PR responses from the existing M3 sample. All four were open. Four ordinary URL preflights each returned the other PR in the intended pair as a suggested comparison. Radar independently created two high-confidence draft tasks, each with a prompt and two pinned sources. A repeat processed zero changes. Each AnyXboxX PR description already cited its victory-fork peer, and the test selected the four inputs. This demonstrates indexing, retrieval of known references and draft generation in a four-source catalog. It does not establish discovery of an unknown solution or volunteer use. No network Discovery queries or deliveries ran. [Original M3 evidence](../../../docs/PORTBRIDGE-M3.md)

| PR pair | Revisions read, in order | Source check and scope |
| --- | --- | --- |
| [AnyXboxX #354](https://github.com/LooperSalty/AnyXboxX/pull/354) and [victory-fork #1289](https://github.com/fxceless/victory-fork/pull/1289) | `5865586f6b8715566959636f7f08c197ca0659de` · `42fdddc7e603e84ebedbd4245cc6d1344075b0c1` | Both eviction paths skip textures when their last fence exceeds the completed fence. This gives the receiving developer a concrete negative control, retaining a texture whose queue work is unfinished. [AnyXboxX guard](https://github.com/LooperSalty/AnyXboxX/blob/5865586f6b8715566959636f7f08c197ca0659de/third_party/victory/crates/victory-gpu/src/resource.rs#L3075) · [victory-fork guard](https://github.com/fxceless/victory-fork/blob/42fdddc7e603e84ebedbd4245cc6d1344075b0c1/crates/victory-gpu/src/resource.rs#L2494) |
| [AnyXboxX #350](https://github.com/LooperSalty/AnyXboxX/pull/350) and [victory-fork #1286](https://github.com/fxceless/victory-fork/pull/1286) | `69a0a8cc33904a77ed8735691fd9966357916b20` · `285af62cc717c1c09d4bfd27d2bccef47671c597` | The PRs discuss memory decommit. The stable patch IDs of their **head commits** differ, respectively `51d7288a9477001d0c8b08c8275dd693467c17d2` and `40b17e55e2ae3198e9c8a8c036d029a06889173d`. The identity hypothesis fails. Radar calls this a possible optimization to compare. All four URL queries kept the unrelated eviction/decommit cross-pairs out of their matches. |

The draft IDs were `rad-dcbc3b775d7358b16ad755fba4023a67` and `rad-ac4d6f18fab78005aaf4fc59dfe77ebd`, respectively. Neither acquired a report or a delivery in this run. At the time of the check the **production** manifest still showed generation `2026-11-26T15:49:46+00:00`. It exposed 16 Lab tasks, neither draft and no dedicated Radar snapshot. These local drafts cannot stand in for a public scheduled intake or a receiving team. [Published manifest](https://akimfomin.github.io/PortBridge/data/site.json)

## What a participant actually did

FrameLab’s maintainer opened its own issue on 24 November, linked the exact Test Lab card and committed the link to the team’s documentation. JoeY54 volunteered, ran four Vulkan cases on each of two AMD devices and stated that Codex built and executed the second run. The FrameLab maintainer reviewed both reports against the pinned test and posted separate approvals. The two devices belonged to one volunteer. [Maintainer’s issue](https://github.com/5headsmartbtw/leonida-framelab/issues/15) · [Pinned link in the project documentation](https://github.com/5headsmartbtw/leonida-framelab/blob/1b1c3cfc371225cd020bf4bfbba50e8c696a86f1/docs/evidence/independent-vulkan-handoff.md#L44) · [Volunteer claim](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7145100395) · [First report](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7147944059) · [Second report and agent disclosure](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7153817545) · [Receiving review](https://github.com/5headsmartbtw/leonida-framelab/issues/15#issuecomment-7160148587)

This is direct evidence of a historical source-to-Lab handoff, use of the volunteer’s agent and independent review. The task was already curated. The sources do not identify Radar as its origin or show the participant copying the Lab URL into the agent. At 20:24 UTC both approved passes and covered AMD were visible on production under the old `awaiting_review` label. M5.1 had already corrected the label in the candidate. There was no new external M5 use in this check. [M5.1 import and approved reports](../lab.md) · [M5.3 prospective test](../m53/assessment.md)

**E2E-01 remains partial.** The positive known-reference case and the unrelated cross-pair controls are reproducible. A freshly checked, independently discovered finding in production remains unobserved. **E2E-02 remains partial.** The draft can be followed through the staged workflow. Historical FrameLab evidence verifies the later human steps on a different card. One public, attributable chain from an automatically generated Radar card through the participant’s own agent and a reviewed report remains open.

## Reproduce

Run the following Python from the repository root with Python 3.11+ and Git. The default replays the four saved source projections below in a temporary database and reads the two immutable public diffs. Set `PORTBRIDGE_E2E_LIVE=1` to obtain four fresh GitHub PR responses instead. The first anonymous read succeeded for all four. A later anonymous repeat hit HTTP 403 rate limiting. Moving heads can also change live results.

```python
import json, os, subprocess, tempfile
from pathlib import Path
from urllib.request import Request, urlopen
from portbridge.catalog import Catalog
from portbridge.github import _item
from portbridge.lab import build_lab
from portbridge.preflight import preflight
from portbridge.radar_scan import refresh

def read(url, limit):
    with urlopen(Request(url, headers={"User-Agent": "PortBridge-intake-check"}), timeout=20) as response:
        data = response.read(limit + 1)
    assert len(data) <= limit
    return data

doc = Path("audit/evidence/m6/e2e-intake.md").read_text(encoding="utf-8")
rows = json.loads(doc.split(chr(96) * 3 + "json\n")[1].split(chr(96) * 3)[0])
with tempfile.TemporaryDirectory() as folder:
    c = Catalog(Path(folder) / "catalog.db", "portbridge/data/seed.json")
    if os.environ.get("PORTBRIDGE_E2E_LIVE") == "1":
        projects = {p["slug"]: p for p in c.projects()}
        names = {p["repo"].lower(): p["repo"] for p in projects.values()}
        for i, row in enumerate(rows):
            project = projects[row["project"]]
            n = int(row["source_id"])
            pr = json.loads(read(f"https://api.github.com/repos/{project['repo']}/pulls/{n}", 2_000_000))
            assert pr["number"] == n and pr["base"]["repo"]["private"] is False
            rows[i] = _item(pr, "pr", project, names)
    c.record_sync({"items": rows}, update_health=False)
    print(refresh(c, online_discovery=False))
    for row in rows:
        result = preflight(c, url=row["url"])
        print(row["status"], row["metadata"]["head_sha"], result["indexed"],
              [(m["right"]["url"], m["basis"], m["relationship"]) for m in result["matches"]])
    print([(t["id"], t["workflow_state"], bool(t.get("prompt")))
           for t in build_lab(c)["tasks"] if t.get("candidate_id")])
    print(refresh(c, online_discovery=False)["seen"])

for repo, sha in [("LooperSalty/AnyXboxX", "69a0a8cc33904a77ed8735691fd9966357916b20"),
                  ("fxceless/victory-fork", "285af62cc717c1c09d4bfd27d2bccef47671c597")]:
    diff = read(f"https://github.com/{repo}/commit/{sha}.diff", 5_000_000)
    assert diff.startswith(b"diff --git ")
    print(subprocess.check_output(["git", "patch-id", "--stable"], input=diff).split()[0].decode())
```

Saved fields used by the reader and matcher follow. User information and raw PR prose are omitted.

```json
[
{"project":"anyxboxx","kind":"pr","source_id":"354","title":"perf(victory-gpu): add fence-safe LRU texture eviction, budget-aware mip clamping, and async reaper","url":"https://github.com/LooperSalty/AnyXboxX/pull/354","status":"open","updated_at":"2026-11-26T19:19:14Z","metadata":{"technical":{"version":5,"terms":["atomic","shader","dxgi","d3d12","bindless"],"discovery_cues":[],"signals":[],"references":["https://github.com/fxceless/victory-fork/pull/1289"],"external_repositories":[]},"head_sha":"5865586f6b8715566959636f7f08c197ca0659de","draft":false}},
{"project":"victory-gta6","kind":"pr","source_id":"1289","title":"gpu: fence-safe LRU texture eviction and budget-aware mip clamping","url":"https://github.com/fxceless/victory-fork/pull/1289","status":"open","updated_at":"2026-11-26T17:22:17Z","metadata":{"technical":{"version":5,"terms":["dxgi","shader","bindless","d3d12"],"discovery_cues":["texture uploads"],"signals":[],"references":[],"external_repositories":[]},"head_sha":"42fdddc7e603e84ebedbd4245cc6d1344075b0c1","draft":false}},
{"project":"anyxboxx","kind":"pr","source_id":"350","title":"perf(victory-gpu): reclaim idle host System RAM via MEM_DECOMMIT and cold pool/DXIL trimming","url":"https://github.com/LooperSalty/AnyXboxX/pull/350","status":"open","updated_at":"2026-11-26T19:19:16Z","metadata":{"technical":{"version":5,"terms":["dxil","d3d12","shader"],"discovery_cues":[],"signals":[],"references":["https://github.com/fxceless/victory-fork/pull/1286"],"external_repositories":[]},"head_sha":"69a0a8cc33904a77ed8735691fd9966357916b20","draft":false}},
{"project":"victory-gta6","kind":"pr","source_id":"1286","title":"perf(victory-gpu): reduce host System RAM footprint via VM decommit and cold pool/DXIL trimming","url":"https://github.com/fxceless/victory-fork/pull/1286","status":"open","updated_at":"2026-11-26T18:50:12Z","metadata":{"technical":{"version":5,"terms":["dxil","shader","d3d12"],"discovery_cues":[],"signals":[],"references":[],"external_repositories":[]},"head_sha":"285af62cc717c1c09d4bfd27d2bccef47671c597","draft":false}}
]
```

Run the offline trust-boundary tests from the same checkout. The three suites returned 17, 9 and 18 passes on the audit machine. They cover withheld results before review, rejected self-review, conflicting outcomes, withdrawal and feedback to Search using controlled actors.

```sh
python -B -m unittest discover -s tests -p test_preflight.py -q
python -B -m unittest discover -s tests -p test_radar_workflow.py -q
python -B -m unittest discover -s tests -p test_lab_reports.py -q
```
