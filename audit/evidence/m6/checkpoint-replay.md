# M6 checkpoint and rollback rehearsal

On November 26, 2026 the preceding scheduled Pages run published 25,426 observations. The anonymous public `data/observations.json` downloaded before deployment was 17,022,692 bytes, SHA-256 `d69a5b42206e0136739b850ed5fb941127056fa5a7bb9037fce2742ef2698924`. [Prior production run](https://github.com/akimfomin/PortBridge/actions/runs/45852310279) · [Its Pages artifact](https://github.com/akimfomin/PortBridge/actions/runs/45852310279/artifacts/15135120357).

The rehearsal imported all of those public observations into an isolated database, created the public Discovery, People and Radar schemas, built a compact checkpoint (19,210,240 bytes in 0.125 s), then restored two independent copies with empty export directories. Private operator state and opaque on-disk remnants are excluded by the public checkpoint command. The checkpoint was newly generated from the published observations. This test did not restore a production database with private activity.

| Code serving the restored copy | Exported observations | Source identities | Export files | Wall time for restore, export and verification |
| --- | ---: | --- | ---: | ---: |
| Local M6 partner revision `99bb59855a3a0042813ca1ed9c29bdfd69c1cddf` · [published checkpoint implementation](https://github.com/akimfomin/PortBridge/blob/a5cf560032ebfcf2872577b91b8bedffc47c9a14/portbridge/backup.py) | 25,426 | all match | 7,665 | 48.454 s |
| Previous public main `56e2262d62c492f4a866c350f3f708c3f694f77f` | 25,426 | all match | 7,645 | 42.640 s |

The M6 release gate validated the recovered export. Both isolated code revisions produced the same full set of source project, kind, source ID and URL tuples. The running site continued to serve its prior publication throughout the rehearsal. File counts and timings can differ as the repository and public dataset change.

```sh
git worktree add --detach ../previous-portbridge 56e2262d62c492f4a866c350f3f708c3f694f77f
curl -fL https://akimfomin.github.io/PortBridge/data/observations.json -o observations.json
python -B audit/m6_checkpoint_replay.py --observations observations.json --rollback-code ../previous-portbridge
```

Compare the input digest for exact reproducibility. While retained, the prior Pages artifact contains the generation used here. Later downloads from the stable URL test the current public corpus.
