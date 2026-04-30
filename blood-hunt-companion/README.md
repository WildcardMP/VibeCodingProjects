# Blood Hunt Companion

Local web app for theorycrafting & gear optimization in *Marvel Rivals: Blood Hunt*. Designed for top-leaderboard players who need real numbers, not beginner guides.

## Documents

- **[`PROJECT.md`](./PROJECT.md)** — architecture, features, build phases.
- **[`RESEARCH.md`](./RESEARCH.md)** — game knowledge: heroes, gear, traits, Arcana, formulas.
- **[`DATA_PIPELINE.md`](./DATA_PIPELINE.md)** — FModel extraction + OCR pipeline implementation guide.
- **[`CLAUDE.md`](./CLAUDE.md)** — operating rules + active phase pointer (Phase 2: OCR ingest end-to-end).

## What's in this repo right now

Phase 1 done. Phase 2 in progress — OCR pipeline plus persistence (gear table + CRUD endpoints) live, no frontend yet.

```
apps/api/                FastAPI backend
  alembic.ini            Alembic migration config
  alembic/               migration scripts
  app/
    main.py              uvicorn entrypoint, wires routers + CORS
    config.py            paths, CORS, env-var settings
    db.py                SQLAlchemy engine, sessionmaker, FastAPI dependency
    schemas/             Pydantic models for gear, hero, trait, arcana, run
    models/              SQLAlchemy ORM (GearORM)
    routers/             FastAPI route modules (gear)
    ocr/                 OCR pipeline (detect, anchors, preprocess, parse, fuzzy,
                                       rarity, templates, debug, pipeline)
    data_loader.py       reads canonical game JSON
  tests/                 pytest suite
  pyproject.toml
data/
  game/                  canonical game data (real or seed)
    *.seed.json          bundled seed catalogs (work without FModel)
    _raw/                drop FModel exports here
    _assets/             user-supplied tier-badge / slot-icon PNGs (see _assets/README.md)
  screenshots/           ingested gear screenshots (gitignored)
  debug/                 OCR debug-image dumps (gitignored, only when BLOOD_HUNT_OCR_DEBUG=1)
  personal.db            SQLite DB created by `make migrate` (gitignored)
tools/
  translate_game_data.py FModel raw → canonical JSON
Makefile
```

## Quickstart

```bash
# 1. Install (creates .venv, installs api+dev deps editable)
make install

# 2. Run tests — proves the translator, OCR helpers, and persistence work
make test

# 3. Initialise / upgrade the SQLite DB
make migrate

# 4. Start the API at http://localhost:8000
make api

# 5. Sanity-check
curl http://localhost:8000/api/health
curl http://localhost:8000/api/game/version
curl http://localhost:8000/api/game/heroes  # uses bundled seed data until you run FModel
curl http://localhost:8000/api/gear         # empty list until you POST your first piece
```

## Gear persistence workflow

The full ingest path is **OCR → review → save → query**:

```bash
# 1. OCR a screenshot (does NOT persist).
curl -F "file=@inventory.png" \
     "http://localhost:8000/api/gear/ingest?width=3840&height=2160&ui_scale=1.0"
# → returns a ParsedGear JSON with per-field confidence.

# 2. Save it (post-review, possibly hand-edited):
curl -X POST http://localhost:8000/api/gear/manual \
     -H 'Content-Type: application/json' \
     -d @parsed_gear_reviewed.json
# → returns the saved GearPiece with id + parsed_at.

# 3. List with filters:
curl "http://localhost:8000/api/gear?hero_id=squirrel_girl&rarity=legendary&min_confidence=0.85"

# 4. Update a field (e.g. mark equipped, edit notes, fix a tier letter):
curl -X PATCH http://localhost:8000/api/gear/42 \
     -H 'Content-Type: application/json' \
     -d '{"is_equipped": true, "notes": "BiS for SG NM160"}'

# 5. Delete:
curl -X DELETE http://localhost:8000/api/gear/42
```

### Endpoints

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/gear/ingest` | OCR-only, returns ParsedGear, no DB write |
| `POST` | `/api/gear/manual` | Persist a ParsedGear; returns 201 + GearPiece |
| `GET`  | `/api/gear` | List; filters: `hero_id`, `slot`, `rarity`, `min_confidence`, `is_equipped`, `limit`, `offset` |
| `GET`  | `/api/gear/{id}` | Single piece or 404 |
| `PATCH`| `/api/gear/{id}` | Partial update; `extended_effects` replaces the whole list when present |
| `DELETE`| `/api/gear/{id}` | 204 on success, 404 otherwise |
| `POST` | `/api/gear/score` | Roll evaluator (Phase 4 F2): `(gear, build)` → 0–100 score + threshold tier + forge action; stateless |
| `POST` | `/api/simulate` | Damage simulator (Phase 3 F1): `(hero, gear, traits, arcana, target)` → per-ability DPS + aggregated `StatTotals` |

## OCR ingest setup

The pipeline is **calibration-free** (per the 2026-04-27 architectural pivot in PROJECT.md §9). Take a full-screen screenshot at any resolution while a gear tooltip is on screen — the pipeline auto-detects the card, anchors regions by proportion, and identifies stats by their text label.

You need:

1. **Tesseract installed** on PATH (`apt install tesseract-ocr`, `brew install tesseract`, or the [Windows installer](https://github.com/UB-Mannheim/tesseract/wiki)). Override the binary location with `BHC_TESSERACT_CMD=/path/to/tesseract`.

2. **Optional template PNGs** at `data/game/_assets/{tier_badges,slot_icons}/*.png` — see [`data/game/_assets/README.md`](./data/game/_assets/README.md). Without these the pipeline falls back to Tesseract-only for tier letters and a base-effect heuristic for slots.

3. **Optional debug dumps**: set `BLOOD_HUNT_OCR_DEBUG=1` and the pipeline writes annotated PNGs of every stage's output to `data/debug/<stage>/`. Invaluable when tuning Stages 1–3 against real screenshots.

## Database & migrations

The app uses SQLite at `data/personal.db` (override with `BHC_DB_PATH`). Schema is managed by Alembic.

```bash
# Bring the DB to head (run after pulling new code or on first install).
make migrate

# Generate a new migration after adding/changing an ORM model.
make migrate-revision m="add runs table"
```

Migrations live in [`apps/api/alembic/versions/`](./apps/api/alembic/versions/). Schema changes follow the cascade in [`CLAUDE.md` §8.2](./CLAUDE.md): Pydantic → SQLAlchemy → Alembic → generated TS types → frontend.

## Continuous integration

Every push to `main` and every PR runs the same triad you'd run locally:

```
ruff check apps/api tools
mypy app                      (strict, in apps/api)
pytest apps/api/tests
```

The workflow lives at [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) (at the repo root, since `blood-hunt-companion/` is a subdirectory of the parent repo). It runs on `ubuntu-latest` against Python 3.11 — the floor declared in `apps/api/pyproject.toml`. Tesseract isn't installed on the runner, so the OCR-fixture tests skip cleanly via `pytest.importorskip` (matching local behavior when fixtures or screenshots aren't ready). A failing CI build blocks merge; fix lint or test breakage before pushing.

## Game-data refresh (per patch)

```bash
# 1. Refresh AES key + mappings from https://www.nexusmods.com/marvelrivals/mods/1717
# 2. Open FModel, point it at MarvelRivals\MarvelGame\Marvel\Content\Paks
# 3. Save Properties (.json) for the DT_* tables listed in DATA_PIPELINE.md §1.4
#    into data/game/_raw/
make extract
```

The translator falls back to bundled `*.seed.json` files if a real export is missing, so the app keeps working even before your first FModel run.

## Status

Phase 2 partially landed: OCR pipeline (with dual-strategy tier detection + slot template matching) plus full gear CRUD persistence backed by Alembic-managed SQLite. **Phase 3 F1 (Damage Simulator) backend** also landed — `POST /api/simulate`. **Phase 4 F2 (Gear Roll Evaluator) backend landed 2026-04-29** — `POST /api/gear/score` returns a 0–100 score, threshold tier (`trash`…`leaderboard_grade`), and a forge action (`smelt`/`use_temporarily`/`keep`/`reroll_low_tiers`/`lock`) for any single gear piece against an explicit or hero-derived stat-weight build context. **237 tests passing** (the OCR-fixture accuracy gate stays skipped until user-supplied screenshots land; see PHASE2_OCR_INPUTS.md).

Still pending in Phase 2 (per [`CLAUDE.md` §7.1](./CLAUDE.md)):
- Real-screenshot OCR fixture suite (≥10 tooltips with hand-labeled `expected.json`).
- User-supplied tier-badge / slot-icon PNGs under `data/game/_assets/`.

Next backend chunks: real Monte-Carlo percentile for F2 (current placeholder = score itself), F4 Forge ROI (Phase 4), F3 Run Logger (Phase 5). Frontend (Next.js in `apps/web/`) lands after backend feature set is complete. See [`PROJECT.md` §9](./PROJECT.md#9-phased-build-plan) for the full plan.
