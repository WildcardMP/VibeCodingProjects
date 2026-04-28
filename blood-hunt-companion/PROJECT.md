# Blood Hunt Companion — Project Specification

> **Audience:** Claude Code (implementation agent) + the user (NM 160 leaderboard player, mains Squirrel Girl & Moon Knight).
> **Goal:** A local web app that turns gear/build optimization for *Marvel Rivals: Blood Hunt* from a guessing game into a measurable, math-backed workflow.
> **Companion documents:** [`RESEARCH.md`](./RESEARCH.md) (game knowledge & sources), [`DATA_PIPELINE.md`](./DATA_PIPELINE.md) (FModel + OCR implementation).

---

## 1. Vision

Blood Hunt is the only PvE mode in Marvel Rivals. The player has cleared Nightmare 160 (max difficulty) and ranks 6th on the global leaderboard. Standard guides are useless at that level — what matters is:

1. **Quantifying** which gear roll, trait node, and Arcana scroll combination produces the highest *effective DPS* against Dracula's enrage.
2. **Avoiding waste** in the Forge — at ~10% legendary chance and 200 K Uru Shards per stack of 10 attempts, every reroll has a measurable expected value.
3. **Tracking runs** to find statistically significant wipe causes and squad compositions.
4. **Removing manual data entry** — the player owns hundreds of gear pieces; typing them in is unacceptable.

The companion app is a **personal min-max workbench**, not a beginner guide.

---

## 2. Non-Goals & Out of Scope

To stay safely on the right side of NetEase's third-party policy ([Marvel Rivals plugin ban precedent](https://marvelrivals.gg/marvel-rivals-bans-third-party-plugins/)), the app will **not**:

- Read, hook, or inject into the running game process.
- Read game memory, network packets, or shader output.
- Provide any in-match telemetry, automated callouts, or PvP advantage.
- Modify game files, paks, or save data.
- Auto-aim, auto-cast, or scripted input of any kind.
- Share or upload other players' data without consent.

The app reads only:

- Static, datamined game files extracted offline by the user with FModel (the same workflow the broader datamining community uses).
- Screenshots taken by the user of their own inventory UI (OCR).
- The user's own self-reported run logs.

---

## 3. Five Core Features

### F1 — Damage Simulator / Theorycrafter

**Problem it solves:** Is +8300 % Precision Damage on a legendary roll actually better than +1200 % Total Output Boost on a different piece, given my current Squirrel Girl trait tree and Arcana?

**Inputs:** Hero, full gear loadout (4 slots), trait allocations, equipped Arcana, target type (boss / horde / Dracula Phase X).

**Outputs:**
- Per-ability tooltip damage and effective DPS.
- Side-by-side comparison of the equipped build vs. a "what if I swap this piece?" candidate.
- Heatmap of which stat the build is most starved for (next-best-stat recommendation).

**Math sources:** Damage formula scaffold in [`RESEARCH.md` §6](./RESEARCH.md), trait scaling pulled from datamined `DT_*` UAssets (see DATA_PIPELINE.md §3).

### F2 — Gear Roll Evaluator

**Problem it solves:** I just rolled a chest piece with several extended effects (legendary gear can show up to 5). Is it leaderboard-grade or vendor trash?

**Inputs:** A single piece of gear (parsed from screenshot OCR, or manually entered). Each piece has 1+ base effects (e.g. armor shows BOTH `Health` and `Armor Value`), an in-game `rating` integer (e.g. 7086), and a `hero` binding.

**Outputs:**
- **Roll Score (0–100)** vs. theoretical maximum for that slot/hero/build.
- **Percentile** vs. a synthetic distribution from datamined `min`/`max` values per stat.
- **Threshold tier:** Trash / Filler / Keep / BiS-candidate / Leaderboard-grade.
- Suggested forge action: keep / reroll extended effects / Uru Shard fodder.

**Why it matters:** Saves hundreds of thousands of Uru Shards per week.

### F3 — Run Logger & Analytics

**Problem it solves:** Why am I wiping at Phase 12 with this Moon Knight Ankh build but not the Spin Kick build?

**Inputs (per run):**
- Difficulty (NM 1–160), squad heroes, equipped gear loadout snapshot, Arcana, outcome (clear / wipe / phase reached), duration, notes.
- Optional: clipboard-paste of post-run screen OCR for damage totals.

**Outputs:**
- Win-rate by hero, by build, by squad composition.
- Phase-of-death distribution (where do I actually die?).
- Uru Shard / Arcana yield per hour by difficulty.
- Statistical confidence flags: "10 runs is not enough to claim Build A > Build B."

### F4 — Forge ROI Calculator

**Problem it solves:** Should I roll my 800 K shards on a fresh chest piece, or shard my five purples for a guaranteed legendary? What's the EV of stack-of-10 rolls at level 60?

**Inputs:** Current shard balance, target slot, current best-in-slot piece's roll score.

**Outputs:**
- Expected number of attempts to beat current piece, given datamined drop tables.
- Cost in shards, time, and opportunity cost (shards not spent on Arcana).
- Break-even threshold: "Don't reroll until your current piece scores below X."

### F5 — Live Build Overlay (Optional, V2+)

**Problem it solves:** Quick reference during a run without alt-tabbing.

A read-only OBS browser source / always-on-top window that shows the currently selected build's trait order, gear targets, and a Dracula phase cheat sheet. **No game-process interaction.** It is just a webpage on top of the game.

---

## 4. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     User's Local Machine                     │
│                                                              │
│  ┌────────────────┐                                          │
│  │ FModel + Repak │── one-time / patch-day extraction        │
│  │ (offline tool) │   → /data/game/*.json                    │
│  └────────────────┘                                          │
│                                                              │
│  ┌────────────────┐    hotkey      ┌──────────────────────┐  │
│  │ Screenshot tool│───────────────▶│  OCR Worker (Python) │  │
│  │ (PrintScreen)  │                │  Tesseract + OpenCV  │  │
│  └────────────────┘                └──────────┬───────────┘  │
│                                               │              │
│                                               ▼              │
│                                    ┌─────────────────────┐   │
│                                    │  FastAPI Backend    │   │
│                                    │  - /gear (POST)     │   │
│                                    │  - /simulate (POST) │   │
│                                    │  - /runs (CRUD)     │   │
│                                    │  - /forge/roi       │   │
│                                    └──────────┬──────────┘   │
│                                               │              │
│                                  ┌────────────┴────────────┐ │
│                                  ▼                         ▼ │
│                          ┌──────────────┐         ┌────────┐ │
│                          │ SQLite (data)│         │ JSON   │ │
│                          │ - gear       │         │ static │ │
│                          │ - runs       │         │ game   │ │
│                          │ - builds     │         │ data   │ │
│                          └──────┬───────┘         └────┬───┘ │
│                                 │                      │     │
│                                 └──────────┬───────────┘     │
│                                            ▼                 │
│                              ┌────────────────────────────┐  │
│                              │   Next.js Frontend (UI)    │  │
│                              │   localhost:3000           │  │
│                              │   - Simulator              │  │
│                              │   - Gear Evaluator         │  │
│                              │   - Run Logger             │  │
│                              │   - Forge ROI              │  │
│                              └────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

Everything runs on `localhost`. No cloud sync in MVP. No auth (single-user machine).

---

## 5. Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | **Next.js 15 + React 19 + TypeScript** | Fast iteration, great component ecosystem, easy local dev. App Router. |
| UI styling | **Tailwind CSS + shadcn/ui** | Production-quality components without design overhead. |
| Charts | **Recharts** (or **visx** for custom heatmaps) | Run analytics, percentile distributions. |
| Backend | **Python 3.11 + FastAPI + Uvicorn** | Tesseract/OpenCV bindings only exist comfortably in Python. Pydantic models double as TS type sources via `datamodel-code-generator`. |
| OCR | **Tesseract 5** + **OpenCV** preprocessing | Open-source, battle-tested, MIT/Apache. Pattern adapted from [`d2r-loot-reader`](https://libraries.io/pypi/d2r-loot-reader). |
| Fuzzy matching | **rapidfuzz** | Stat-name correction post-OCR (e.g. "Precision Oamage" → "Precision Damage"). |
| DB | **SQLite** via **SQLAlchemy 2.0** | Single file, zero-config, perfect for personal data. |
| Game data | **JSON files** extracted by FModel | Static, version-controlled per game patch. See [`DATA_PIPELINE.md`](./DATA_PIPELINE.md). |
| Process orchestration | **`concurrently`** (npm) or a single `make dev` target | Spin up FastAPI + Next.js + OCR worker together. |
| Packaging (V2) | **Tauri** wrapper | Optional desktop shell with global hotkey support. |

**Deliberately not chosen:**
- Electron — heavier than Tauri, no benefit here.
- Postgres / cloud DB — unnecessary; one user, one machine.
- An ORM-less raw SQL approach — schema will evolve every patch; SQLAlchemy migrations save time.
- A separate Rust OCR pipeline — Python's ecosystem is faster to iterate in for v1; revisit only if perf becomes a problem.

---

## 6. Repository Layout

```
blood-hunt-companion/
├── README.md
├── PROJECT.md                  ← this file
├── RESEARCH.md                 ← game knowledge
├── DATA_PIPELINE.md            ← FModel + OCR specifics
├── package.json                ← root workspace, runs both apps
├── Makefile                    ← `make dev`, `make extract`, `make test`
│
├── apps/
│   ├── web/                    ← Next.js frontend
│   │   ├── src/app/
│   │   │   ├── simulator/
│   │   │   ├── gear/
│   │   │   ├── runs/
│   │   │   └── forge/
│   │   ├── src/components/
│   │   ├── src/lib/api.ts      ← typed FastAPI client
│   │   └── src/types/          ← generated from Pydantic
│   │
│   └── api/                    ← FastAPI backend
│       ├── pyproject.toml
│       ├── app/
│       │   ├── main.py
│       │   ├── routers/
│       │   │   ├── gear.py
│       │   │   ├── simulate.py
│       │   │   ├── runs.py
│       │   │   └── forge.py
│       │   ├── models/         ← SQLAlchemy
│       │   ├── schemas/        ← Pydantic
│       │   ├── services/
│       │   │   ├── damage_calc.py
│       │   │   ├── roll_score.py
│       │   │   └── forge_roi.py
│       │   ├── ocr/
│       │   │   ├── pipeline.py
│       │   │   ├── preprocess.py
│       │   │   ├── parse.py
│       │   │   └── fuzzy.py
│       │   └── data_loader.py  ← reads /data/game/*.json
│       └── tests/
│
├── data/
│   ├── game/                   ← FModel exports (JSON)
│   │   ├── heroes.json
│   │   ├── traits.json
│   │   ├── gear_stats.json
│   │   ├── arcana.json
│   │   └── version.json        ← game patch version
│   ├── personal.db             ← SQLite (gitignored)
│   └── screenshots/            ← OCR input archive (gitignored)
│
└── tools/
    └── extract_game_data.md    ← step-by-step FModel guide
```

---

## 7. Data Models (SQLite, MVP)

```sql
-- Gear pieces owned by the player
CREATE TABLE gear (
  id              INTEGER PRIMARY KEY,
  name            TEXT,                     -- in-game item name, e.g. "Runic Armor"
  slot            TEXT NOT NULL,            -- 'weapon'|'armor'|'accessory'|'exclusive' (RESEARCH §3)
  hero            TEXT,                     -- in-game hero display name, e.g. "Moon Knight"
  hero_id         TEXT,                     -- canonical slug for joins, e.g. "moon_knight"
  rarity          TEXT NOT NULL,            -- 'normal'|'advanced'|'rare'|'epic'|'legendary'
  level           INTEGER NOT NULL,         -- 1..60 (cap matches hero level cap)
  rating          INTEGER NOT NULL DEFAULT 0, -- tooltip overall rating, e.g. 7086
  base_effects_json TEXT NOT NULL,          -- [{name, value}, ...] — 1+ base rows per piece
  extended_effects_json TEXT NOT NULL,      -- [{stat_id, tier, value}, ...] — 0..5 rows per rarity
  source_screenshot TEXT,                   -- path to /data/screenshots/...
  ocr_confidence  REAL,
  field_confidences_json TEXT NOT NULL DEFAULT '{}',
  parsed_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  is_equipped     BOOLEAN DEFAULT 0,
  notes           TEXT
);

CREATE TABLE builds (
  id              INTEGER PRIMARY KEY,
  hero_id         TEXT NOT NULL,
  name            TEXT NOT NULL,
  trait_alloc_json TEXT NOT NULL,           -- {node_id: points}
  arcana_json     TEXT NOT NULL,            -- [scroll_id, ...]
  gear_loadout_json TEXT NOT NULL,          -- {slot: gear_id}
  created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE runs (
  id              INTEGER PRIMARY KEY,
  difficulty      INTEGER NOT NULL,         -- 1..160
  build_id        INTEGER REFERENCES builds(id),
  squad_json      TEXT NOT NULL,            -- [hero_id, ...]
  outcome         TEXT NOT NULL,            -- 'clear'|'wipe'
  phase_reached   INTEGER,                  -- 1..12
  duration_seconds INTEGER,
  shards_earned   INTEGER,
  notes           TEXT,
  played_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_runs_build ON runs(build_id);
CREATE INDEX idx_gear_hero_slot ON gear(hero_id, slot);
```

> **Vocabulary note (2026-04-27):** rarity values were renamed to match the
> in-game subtitles confirmed against user-captured screenshots. Old `common`
> → `normal`, old `uncommon` → `advanced`. Per-rarity extended-effect counts:
> normal 0 / advanced 1 / rare 2 / epic 3 / legendary up to 5. Migration
> `0003_vocabulary_corrections` renames any persisted values and folds the
> previous scalar `base_effect` + `base_value` pair into the new
> `base_effects_json` list (every gear piece has 1+ base effects).

---

## 8. Key API Endpoints (MVP)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/gear/ingest` | Accept screenshot upload → OCR → parsed gear → DB. Returns parsed object + confidence. |
| `POST` | `/api/gear/manual` | Manually create/edit a gear piece. |
| `GET`  | `/api/gear` | List gear with filters (hero, slot, rarity, min score). |
| `POST` | `/api/gear/score` | Score a gear piece against a target build. Stateless for "what if" comparisons. |
| `POST` | `/api/simulate` | Run damage simulation for a (hero, build, target) tuple. Returns per-ability DPS and a stat-sensitivity table. |
| `POST` | `/api/runs` | Log a run. |
| `GET`  | `/api/runs/analytics` | Aggregate stats: win-rate by build, phase-of-death distribution, etc. |
| `POST` | `/api/forge/roi` | Forge ROI calc: target slot, current best, shard balance → EV table. |
| `GET`  | `/api/game/version` | Current loaded game-data patch version (so frontend can show "data outdated" banners). |

All endpoints local-only, CORS open to `localhost:3000`.

---

## 9. Phased Build Plan

### Phase 0 — Bootstrap (½ day)

- Scaffold repo with the layout in §6.
- `make dev` runs Next.js + FastAPI together.
- Empty SQLite, empty `/data/game/`, hard-coded "Hello Squirrel Girl" page.
- CI: ruff + mypy on Python, eslint + tsc on TS, GitHub Actions on push.

### Phase 1 — Static Game Data (1 day)

- Run FModel extraction following [`DATA_PIPELINE.md`](./DATA_PIPELINE.md) §1–3.
- Hand-translate the most important `DT_*` UAssets into the JSON schema in §10 of this doc.
- Implement `data_loader.py` and `/api/game/version`.
- Frontend: read-only "Codex" page that browses heroes, traits, Arcana, gear stat catalog. Sanity check.

**Exit criteria:** I can browse every Squirrel Girl trait node and every Arcana scroll on `localhost:3000`.

### Phase 2 — Gear Ingest via OCR + Persistence (3–4 days)

**Architectural pivot (2026-04-27):** OCR pipeline is **calibration-free** and uses **content-based stat identification** rather than fixed positional bounding boxes.

**Why the pivot:**
- The Marvel Rivals gear tooltip can appear anywhere on screen depending on what the user is hovering, so fixed-position calibration is brittle.
- Stats within the extended-effects block can appear in any order on any given gear roll, so reading "row 1 = Attack Power" by position is incorrect.
- The companion app must work for any user at any resolution with zero setup — calibration is a non-starter for shareability.

**Pipeline stages:**

1. **Tooltip card detection.** OpenCV-based detection of the tooltip's bounding box on the screenshot using edge detection + contour filtering. Tooltip has consistent border style and semi-opaque background that distinguishes it from the game world behind it. Output: `(x, y, w, h)` of the card.

2. **Anchor detection inside the card.** Detect structural elements with known *relative* positions within the card: rarity badge location, item name region, base-effect divider, extended-effects block. All measurements proportional to detected card dimensions, never absolute pixels.

3. **Row segmentation.** The extended-effects block is segmented into rows by detecting horizontal whitespace gaps. Number of rows is detected, not assumed — supports tooltips with 1, 2, 3, or 4 extended effects.

4. **Row content extraction.** For each detected row, OCR the text to read stat label and value. Fuzzy-match the label against the canonical stat list in `app/ocr/fuzzy.py` to identify which stat it is. **Stat identity is content-based, not position-based.**

5. **Tier indicator extraction.** Template-match each row's tier indicator against the reference tier badge PNGs in `data/game/_assets/tier_badges/`.

6. **Confidence scoring + manual correction.** Every extracted field carries a confidence score. Low-confidence fields surface to the user in the UI for manual review and correction.

**Implementation tasks:**

- Replace `tools/ocr_calibration.py` and the calibration JSON loading logic with `app/ocr/detect.py` (tooltip detector) and `app/ocr/anchors.py` (relative-position anchor finder).
- Update `app/ocr/pipeline.py` to chain: detect → anchor → segment rows → extract content → score confidence.
- Keep the existing tier-badge template matching (already implemented in `app/ocr/templates.py`).
- Keep the existing fuzzy matching (already implemented in `app/ocr/fuzzy.py`).
- `/api/gear/ingest` endpoint exists; manual CRUD endpoints (`/api/gear/manual`, GET/PATCH/DELETE) already shipped in Phase 2 §7.0.
- Frontend: drag-drop screenshot or paste-from-clipboard. Show parsed result with per-field confidence, allow manual correction, save.

**User-facing inputs (one-time):**

- 5 tier badge reference PNGs (S/A/B/C/D), tightly cropped from any gear screenshot.
- 4 slot icon reference PNGs (weapon/armor/accessory/exclusive), tightly cropped.
- 10+ test fixture screenshots paired with hand-labeled `expected.json` ground truth, used by automated tests to verify pipeline accuracy.

**Removed from previous architecture:**

- `tools/ocr_calibration.py` — no longer needed.
- Per-resolution calibration JSONs in `data/calibration/` — no longer needed.
- Hard-coded bounding box configuration — replaced by detected anchors.

**Exit criteria:** Drop ten screenshots of real gear at any resolution with the tooltip in any position, ≥9 parse correctly with no manual edits, and the saved pieces survive an API restart. Pipeline runs end-to-end with zero user configuration.

### Phase 3 — Damage Simulator MVP (2 days)

- Encode Squirrel Girl Burst Acorn and Moon Knight Ankh ability formulas first (RESEARCH.md §6).
- Implement `damage_calc.py` taking (hero, build, target) → per-ability DPS.
- Frontend: Simulator page with build editor (gear loadout dropdowns, trait allocator, Arcana picker) and live DPS readout.
- Side-by-side compare two builds.

**Exit criteria:** Simulator's Burst Acorn DPS for my current build is within ±10 % of in-game training-room measurement.

### Phase 4 — Roll Evaluator & Forge ROI (1–2 days)

- `roll_score.py`: compute (0–100) score using stat priority weights from RESEARCH.md §3.4 + datamined min/max from `gear_stats.json`.
- `forge_roi.py`: monte-carlo using datamined drop rates.
- Frontend: Gear page shows score + threshold tier; Forge page shows EV calculator.

**Exit criteria:** I trust the score enough to vendor a piece based on it without second-guessing.

### Phase 5 — Run Logger & Analytics (2 days)

- `/api/runs` CRUD + `/api/runs/analytics`.
- Quick-log form (hotkey-accessible).
- Charts: win-rate by build (with Wilson confidence intervals), phase-of-death distribution, shards/hour by difficulty.

**Exit criteria:** After 50 logged runs, I get a meaningful "your Ankh build clears Phase 12 23 % more often than your Spin Kick build (n=24, p<0.05)" callout.

### Phase 6 — Polish & Optional V2 (open-ended)

- Add remaining 4 heroes' damage formulas.
- Live overlay (F5).
- Export/import build JSON for sharing with squad.
- Tauri packaging.

---

## 10. Game Data JSON Schemas (target shapes)

These are the contracts FastAPI consumes. The exact UAsset → JSON mapping is in [`DATA_PIPELINE.md`](./DATA_PIPELINE.md). Field names are illustrative; actuals depend on the in-game DataTable column names.

```jsonc
// data/game/heroes.json
[
  {
    "id": "squirrel_girl",
    "display_name": "Squirrel Girl",
    "abilities": [
      {
        "id": "burst_acorn",
        "name": "Burst Acorn",
        "tags": ["projectile", "aoe"],
        "base_damage": 80,
        "scaling": [
          { "stat": "precision_damage", "coefficient": 1.0 },
          { "stat": "total_output_boost", "coefficient": 1.0 }
        ],
        "cooldown": 6.0
      }
      // ...
    ]
  }
]

// data/game/traits.json
[
  {
    "hero_id": "squirrel_girl",
    "tree": "gold",      // 'gold' | 'blue' | shared
    "node_id": "rodent_plague",
    "max_points": 5,
    "effects": [
      { "stat": "vulnerability_inflicted", "per_point": 0.09 }
    ],
    "prerequisites": ["squirrel_storm"]
  }
]

// data/game/gear_stats.json
[
  {
    "stat_id": "precision_damage",
    "display_name": "Precision Damage",
    "applies_to_slots": ["weapon", "armor", "accessory", "exclusive"],
    "tiers": [
      { "tier": "D", "min":   30, "max":  100 },
      { "tier": "C", "min":  100, "max":  400 },
      { "tier": "B", "min":  400, "max": 1500 },
      { "tier": "A", "min": 1500, "max": 4000 },
      { "tier": "S", "min": 4000, "max": 8500 }
    ]
  }
]

// data/game/arcana.json
[
  {
    "id": "scroll_of_conquest",
    "name": "Scroll of Conquest",
    "tier": "legendary",
    "effects": [
      { "stat": "total_damage_bonus", "value": 0.30 }
    ]
  }
]
```

---

## 11. Damage Formula Skeleton (`damage_calc.py`)

Pseudo-code; numeric coefficients land in `data/game/*.json` so the formula stays generic.

```python
def simulate(hero, build, target):
    abilities = load_abilities(hero.id)
    stat_totals = aggregate_stats(build.gear, build.traits, build.arcana)
    results = []

    for ability in abilities:
        base = ability.base_damage
        # Multiplicative bucket: total output boost
        out = base * (1 + stat_totals.total_output_boost)
        # Additive bucket: total damage bonus + situational (boss, close-range, ...)
        out *= (1 + stat_totals.total_damage_bonus + situational_bonus(target, stat_totals))
        # Crit / precision are rolled probabilistically; report expected value
        if ability.can_precision:
            p = stat_totals.precision_rate
            out = (1 - p) * out + p * out * (1 + stat_totals.precision_damage)
        # Vulnerability multiplier from target debuffs (e.g. Rodent Plague stacks)
        out *= (1 + target.vulnerability)
        results.append({"ability": ability.id, "expected_hit": out, "dps": out / ability.cooldown})

    return {
        "per_ability": results,
        "stat_totals": stat_totals.dict(),
        "sensitivity": stat_sensitivity(build, target)  # ∂DPS/∂stat — drives "what to upgrade next"
    }
```

---

## 12. Risk Register

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Game patch breaks datamined schemas** | High (every patch) | Version JSON files; show "data outdated — re-run FModel" banner; keep extraction guide one command away. |
| **OCR accuracy <90 % on user's resolution** | Medium | Calibration-free pipeline (Stage 1 detect, Stage 2 proportional anchors); per-field manual correction UI; fuzzy-match catalog reduces typo errors; debug-image dumps via `BLOOD_HUNT_OCR_DEBUG=1` for tuning. |
| **NetEase tightens third-party policy** | Low–Medium | App is read-only on offline files & user screenshots — same posture as the broader datamining community. No process hooks. |
| **Damage formula diverges from in-game reality** | Medium | A/B against training-room measurements; expose coefficients in JSON for fast tuning. |
| **Sample-size confusion in run analytics** | Medium | Wilson confidence intervals on every win-rate; refuse to compare builds with n<10. |
| **AES key rotation in UE5.3 paks** | Low | Nexus Mods #1717 community keeps keys current; document where to refresh. |

---

## 13. Definition of Done — MVP

The MVP is "shippable to the user's own machine" when **all** of the following are true:

1. `make dev` brings up the full stack with one command on a fresh clone.
2. FModel extraction produces all five JSON files in `/data/game/`.
3. Dropping ≥10 inventory screenshots into the Gear page parses ≥9 cleanly.
4. The Simulator returns Burst Acorn and Ankh DPS within ±10 % of training-room reality.
5. The Gear Evaluator can recommend "keep / shard / reroll" on every piece in the user's inventory.
6. The Forge ROI page produces a defensible EV table for a stack-of-10 reroll.
7. README documents the FModel one-time setup, the OCR template-asset capture (per PHASE2_OCR_INPUTS.md), and how to relaunch after a game patch.

Everything beyond is V1+.

---

## 14. Open Questions (resolve during build)

1. ~~**Slot count & names**~~ — Resolved per RESEARCH.md §3: four slots, named **Weapon / Armor / Accessory / Exclusive**. `GearSlot` literal in `schemas/common.py` and `applies_to_slots` in seed data use these names.
2. **Universal vs. hero-specific gear** — confirm whether legendary pieces are bound to a hero or transferable.
3. **Arcana drop rates** — datamined or empirical? If absent from UAssets, treat as user-tracked in `runs.shards_earned` analytics until a sample emerges.
4. **Boss damage stacking** — does Boss Damage multiply with Total Damage Bonus or Output Boost? Empirical A/B in training room during Phase 3.

These do not block scaffolding; they get answered by the time Phase 3 finishes.
