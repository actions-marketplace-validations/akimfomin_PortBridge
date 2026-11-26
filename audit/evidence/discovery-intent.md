# M5.1 Discovery holdout — intent before the search

Recorded 2026-11-26 18:32:13 UTC. The next operation after recording this file is a search of PortBridge. The open PR was selected as the newest open AnyXboxX PR in the first page of the GitHub API at selection time. No Discovery search or ranking was used to select it.

- Origin: https://github.com/LooperSalty/AnyXboxX/pull/429
- Head at selection: `c0a11c0b2b20991e4443580acfe2ae90b3655cb9`
- Public change: a reserved texture can release standard-mip tile runs back to a pool when the level is no longer marked as held or card-written.
- Question for the author: what evidence can validate when recycled physical tiles may be bound to another texture while earlier work may still be queued?
- Fixed query: `D3D12_TILE_RANGE_FLAG_NULL UpdateTileMappings reclaim unmapped mip tiles before heap reuse fence completion`
- Count a hit only if the returned source contains an independently checkable implementation, specification rule or focused test about ordering a tiled-resource unmap/remap and subsequent reuse. A generic eviction policy, memory-budget tuning or unrelated barrier is insufficient. This asks for a possible review check and does not presume a bug.
- Run one ordinary Discovery CLI query with the typed text and origin URL on the checked-in index; preserve its unedited rank order up to five. Also inspect the normal online automatic Discovery channel for the single source observation. Record the two outputs separately, including empty or unavailable outcomes. Do not hand-select a comparison partner or tune the query after inspection. A later rerun may see different online sources.
