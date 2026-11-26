# Dev map tooling

Redraws the [dev map](https://github.com/luizvilla/test_bench_code/issues/1) from the tracker alone. Ported from luizvilla/Theia `tools/devmap`, with the luizvilla/Core Safety-map conventions (out-of-scope nodes, 👤 `wayfinder:luiz`, repo copy in [docs/map.md](../../docs/map.md)).

```sh
python3 tools/devmap/devmap.py --dry-run   # what would change
python3 tools/devmap/devmap.py             # write it; then commit docs/map.md
python3 -m unittest discover -s tools/devmap/tests
```

Needs Python ≥ 3.11 and `gh` logged in. Run it after any ticket opens, closes, is claimed or is blocked; running it twice changes nothing.

- **Colours** from each map ticket: closed done (green); claimed in progress (purple), or stale (red, ⏳) after `stale_days` without a comment, commit or update; open blocker blocked (orange); otherwise takeable (blue). Fog grey dashed, out of scope white dashed.
- **Solid arrows** are GitHub's blocking links between map tickets (transitive ones dropped). Record a dependency as a blocking link, not in the drawing.
- **[layout.toml](layout.toml)** holds what the tracker can't: groups, short labels, done-before-the-map, fog and out-of-scope nodes, dotted arrows, the way to the destination. An unplaced ticket shows under "New tickets".
- **Resume here** lists claimed tickets with their last comment and last commit (`Refs #n` / `Closes #n` / `(#n)`).
- **GitHub Project:** off until `project_owner` / `project_number` are set in layout.toml (fields Status, Slice, Kind as in Theia).
