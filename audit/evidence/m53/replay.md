# Replay the prospective comparison

Run commands from the checkout containing this audit. The two product worktrees must use the revisions below. Both public snapshots use the release's own shipped seed and a fresh SQLite catalog for every PR.

```sh
git worktree add --detach ../m53-replay-baseline df8cfd879c17df04644127c35330ef07407e9392
git worktree add --detach ../m53-replay-candidate 10182c8c3bb66c25f67e16a6e49fc3d3e38e485a
python audit/m53_replay.py --code ../m53-replay-baseline --arm baseline
python audit/m53_replay.py --code ../m53-replay-candidate --arm candidate
```

The default offline mode replays the released engine from its frozen production-normalized PR observations and exact bounded search responses. It checks the selected Git product tree and rejects missing query responses. It compares the full result object, including the subject, order, source route and status. Each observation belongs to the arm that generated it. This mode omits URL resolution and prose extraction.

To run the **ordinary URL-only entry point** add `--public-inputs` to both commands. This contacts GitHub once for each public PR, checks its title, head and full UTF-8 body hash, then applies the public snapshot status, labels, update and verified creation times. Search pages stay frozen. Upstream edits or a core rate limit can prevent public rehydration. In the original independent evaluation use `--raw PATH` with the privately frozen origin file instead. That reproduces launch through `search_link(catalog, url)` and normalizes the complete text using each release. SHA-256 of the private file is `7017b0e3d98e3049ff99b607abd0b309f149e5909da2178d005d6ee933e08404`. No private file is required for the default check. [Acquisition verification](origin-verification.json)

Each unique search request was captured once under the exact URL, including all repo qualifiers and date constraints. Both arms consume the same captured first page whenever their query URLs match. A new arm-specific URL is a different query, so its own actual first page is preserved. Failures and partial pages keep their status. Only field projections consumed by these engines are redistributed. [Shared responses](search-responses.json) / [M5.2 transport](baseline-transport.json) / [M5.3 transport](candidate-transport.json)
