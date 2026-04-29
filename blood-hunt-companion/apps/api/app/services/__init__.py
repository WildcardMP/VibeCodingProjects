"""Application services — pure business logic, no I/O.

* `stat_aggregator` — fold gear + traits + arcana into a `StatTotals` pool.
* `damage_calc`     — turn `(hero, StatTotals, target)` into per-ability DPS.

These are pure functions: no DB session, no HTTP, no Tesseract. Routers in
`app/routers/` orchestrate the I/O and call into here. Tests live under
`tests/services/` and don't need any native deps.

Phase 4 services (`roll_score`, `forge_roi`) will land here later in their
own modules — keep the one-concern-per-module split per CLAUDE.md §3.4.
"""
