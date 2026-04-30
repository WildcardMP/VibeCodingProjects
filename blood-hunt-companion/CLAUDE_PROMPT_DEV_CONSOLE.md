# Claude Code Prompt — Stopgap Interactive Console

> Drop into Claude Code as a single message, or save in repo root and trigger with:
> `Read and execute the instructions in CLAUDE_PROMPT_DEV_CONSOLE.md.`

---

## Context

The user is a NM 160 leaderboard player who wants to **interact with the F1 Damage Simulator and F2 Roll Evaluator (and F4 Forge ROI if landed) right now**, without waiting for the planned Next.js frontend (Phase 3 deliverable per `PROJECT.md` §9, weeks of work).

This prompt builds a **single-file static HTML console** served by the existing FastAPI app at `/console`. User opens `http://localhost:8000/console` in any browser → fills in forms → sees results. No build system, no npm, no Tauri wrapper, no installer. **Not** the planned `apps/web/` Next.js frontend — that work is unaffected.

This is **explicitly a throwaway stopgap**. When the real frontend lands, this file may stay or be deleted with no migration cost.

---

## What you are building

### In scope (this PR)

1. **Static HTML file** at `tools/dev_console/index.html` — vanilla HTML + CSS + JS, no dependencies. Three sections:
   - **Damage Simulator** — POST `/api/simulate`
   - **Roll Evaluator** — POST `/api/gear/score`
   - **Forge ROI Calculator** — POST `/api/forge/roi` (graceful fallback if endpoint 404s — see below)
2. **FastAPI static mount** in `app/main.py` — conditionally mount `tools/dev_console/` at `/console` if the directory exists.
3. **One small test** confirming the route serves HTML when the directory is present.
4. **README addition** — one paragraph in `README.md` pointing users to `localhost:8000/console` after `make api`.

### Anti-scope (do NOT do this PR)

- **No `apps/web/` work.** Do not scaffold Next.js, don't touch `apps/web/`. The console is a separate dev tool at `tools/dev_console/`.
- **No build system.** No npm, no webpack, no Vite, no Tailwind, no React, no jQuery, no any framework. Vanilla HTML + CSS in `<style>` + JS in `<script>`.
- **No external CDN dependencies.** No `<script src="https://...">`. Single self-contained file.
- **No localStorage / sessionStorage.** State lives in memory only — page reload resets it.
- **No auth, no analytics, no telemetry.**
- **Do not modify** any `app/services/*`, `app/schemas/*`, `app/routers/*`, `app/ocr/*`. Console only consumes existing endpoints.
- **No CORS changes.** Console is served same-origin from FastAPI; CORS doesn't apply.
- No new Python dependencies. `fastapi.staticfiles.StaticFiles` is already in FastAPI core.

---

## Required reading

- `CLAUDE.md` §3 (operating rules), §3.8 (local-only architecture), §3.9 (communication style — no filler), §6 (tech stack — note: this prompt deliberately doesn't use the locked stack because the stopgap is below the architectural line), §12 (anti-patterns — especially "❌ Adding a feature flagged 'for future' that has no current call site").
- `PROJECT.md` §3 F1, §3 F2, §3 F4 (problem statements; the console exposes exactly these features).
- `apps/api/app/main.py` — current FastAPI entrypoint, where the `app.mount(...)` call goes.
- `apps/api/app/schemas/simulation.py` — `SimulationRequest` shape (what the simulator form posts).
- `apps/api/app/schemas/roll_score.py` — `RollScoreRequest` shape (what the roll evaluator form posts).
- `apps/api/app/schemas/forge.py` — `ForgeROIRequest` shape if F4 has landed; else verify the file's absence and design the forge section to gracefully detect.
- `apps/api/app/schemas/gear.py` — `ParsedGear` shape (the roll evaluator paste-gear field accepts this).

---

## Plan format

Per `CLAUDE.md` §3.1, write a plan **before** code. Plan must cover:

1. **Files I will create / modify** — concrete paths.
2. **The static-mount call** — exact location in `app/main.py` and the directory-existence guard.
3. **Tests I will add** — one test file or test addition; name and assertion.
4. **F4 endpoint detection strategy** — see "Graceful F4 fallback" below; state which approach you took.
5. **Open questions** — only if any. The CSS / layout choices are yours; don't ask.

---

## Detailed spec

### 1. The HTML file — `tools/dev_console/index.html`

Single file. Structure:

```
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Blood Hunt Companion — Dev Console</title>
  <style>
    /* Inline CSS. Dark theme. CSS Grid layout. Color-coded threshold pills. */
  </style>
</head>
<body>
  <header>
    <h1>Blood Hunt Companion — Dev Console</h1>
    <p class="subtitle">Stopgap interaction layer. Real frontend lands at apps/web/.</p>
  </header>

  <main>
    <section id="simulator">
      <h2>Damage Simulator</h2>
      <form>...</form>
      <pre class="result"></pre>
    </section>

    <section id="evaluator">
      <h2>Roll Evaluator</h2>
      <div class="preset-buttons">
        <button data-fixture="01">Load Runic Armor</button>
        <button data-fixture="02">Load Scepter of Rites</button>
        <button data-fixture="03">Load Alchemy Amulet</button>
      </div>
      <form>...</form>
      <pre class="result"></pre>
    </section>

    <section id="forge">
      <h2>Forge ROI</h2>
      <form>...</form>
      <pre class="result"></pre>
    </section>
  </main>

  <script>
    /* Inline JS. fetch() against /api/*. */
  </script>
</body>
</html>
```

#### 1.1. Damage Simulator section

Form fields:
- `hero_id` — `<select>` with `squirrel_girl` and `moon_knight` options (read live from `GET /api/game/heroes` on page load to populate; fallback to those two if fetch fails).
- `target.target_type` — radio buttons: `boss` / `horde` / `elite`. Default: `horde`.
- `target.is_boss` — derived from `target_type == "boss"`. Mirror the F1 schema.
- `target.is_close_range` — checkbox. Default unchecked.
- `target.is_healthy` — checkbox. Default unchecked.
- `target.vulnerability` — number input, 0–2.0, step 0.05. Default 0.
- `gear` — textarea labeled "Gear (paste JSON array)". Default: `[]`. User can paste a list of `ParsedGear` objects to model their loadout.
- `trait_alloc`, `arcana_realm`, `arcana_in_run` — single textarea each labeled "Traits / Arcana Realm / Arcana In-Run (paste JSON)". Defaults: `{}`, `{}`, `[]`.
- "Run Simulation" submit button.

On submit:
- Build the request body matching `SimulationRequest`.
- `fetch("/api/simulate", { method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(req) })`.
- Display the response in the `<pre class="result">`. Format:
  - **Per-ability table** — ability name, expected_hit, dps, breakdown summary.
  - **Stat totals** — formatted dict.
  - **Sensitivity** — top 5 stats by absolute partial derivative.
  - **Raw JSON** in a collapsed `<details>` for power-user inspection.

Error handling: 4xx / 5xx → show the response body's `detail` field in red. Network errors → "API unreachable. Is `make api` running?"

#### 1.2. Roll Evaluator section

Three fixture preset buttons that load the user's existing fixtures by fetching `apps/api/tests/fixtures/ocr/fixture_01/expected.json` (etc.) from a static-served path or by hardcoding the JSON content directly into the JS (simpler, no extra mounts). **Hardcode them inline** — they're three small JSON objects, copy them from the user's repo at `apps/api/tests/fixtures/ocr/fixture_0{1,2,3}/expected.json` if present at build time. If the fixtures don't exist yet at the time you run this prompt (only ef464a4 fixture batch shipped them), grep the repo and inline whatever's there.

Form fields:
- "Gear (paste JSON)" — textarea pre-fillable by the preset buttons. Schema is `ParsedGear`.
- `build.hero_id` — select (same as simulator).
- `build.ability_id` — select, populated based on chosen hero.
- `build.stat_weights` — optional textarea labeled "Custom stat weights (optional, paste JSON dict)".
- "Score Gear" submit button.

On submit, POST to `/api/gear/score` with `{ gear, build }` matching `RollScoreRequest`.

Display the response with:
- **Score** — large number, color-coded by threshold pill:
  - `trash` → red
  - `filler` → orange
  - `keep` → yellow
  - `bis_candidate` → light green
  - `leaderboard_grade` → gold
- **Threshold + forge action** — text label.
- **Explanation** — quoted sentence.
- **Breakdown table** — per-stat: weight, tier, value, normalized contribution.
- **Uncatalogued stats** — if non-empty, render as a warning panel: "These stats aren't in the catalog and contributed 0: <list>."
- **Raw JSON** in a collapsed `<details>`.

#### 1.3. Forge ROI section — with graceful F4 fallback

On page load, `fetch("/api/forge/roi", { method: "OPTIONS" })` (or HEAD, or just try a tiny POST and check 404 vs 422). If the endpoint returns 404, **show a placeholder**:

```
Forge ROI not implemented yet.
Run CLAUDE_PROMPT_PHASE4_FORGE_ROI.md and refresh this page.
```

If it returns anything else (including 422 from a malformed probe), show the form.

Form fields:
- `slot` — select: weapon / armor / accessory / exclusive.
- `hero_id` — select.
- `hero_level` — number input, default 60, range 1–60.
- `current_best` — textarea, paste a `ParsedGear` (optional; empty = no current piece).
- `build.hero_id` — auto-derived from `hero_id`.
- `shard_balance` — number input (optional).
- `n_simulations` — number input, default 10000, range 100–200000.
- `seed` — number input (optional).
- "Calculate ROI" submit button.

On submit, POST to `/api/forge/roi`.

Display:
- **Recommendation** — large text, color-coded:
  - `lock` → gold
  - `hold` → yellow
  - `reroll` → green
  - `warn_low_probability` → red
- **Expected attempts to beat current** — formatted as float with 1 decimal.
- **Expected shard cost** — formatted with thousands separators.
- **Distribution** — p10 / p50 / p90 / mean as a small bar chart (use `<div>` with width % styling — no charting library).
- **Breakeven score threshold**.
- **If `shard_balance` provided**: "With your current shard balance, you can afford N attempts and have X% chance of beating current."
- **Explanation** — quoted sentence.
- **Raw JSON** in collapsed `<details>`.

#### 1.4. CSS / layout

- Dark theme. Background `#0c0e14` or similar. Text `#e0e0e0`.
- Three sections stacked vertically. Each section has padding, a left-side form (max-width ~480px), and the result panel below the form (full-width).
- Threshold pills: rounded badges with background-color matching the recommendation.
- Distribution bar chart for forge ROI: simple `<div style="width: X%">` with labels.
- Mobile: doesn't matter. This is a desktop dev tool.
- No animations beyond a subtle "loading..." state on submit buttons.

#### 1.5. JS guidelines

- Use `fetch` + async/await. No callback hell.
- One global `state = {}` for cross-section data (e.g., `state.heroes` populated on page load).
- Pretty-print JSON results with 2-space indent.
- Don't use ES modules — single inline `<script>` tag, top-level `const`s and `function`s. No module bundler.
- No `console.log` left in the final code.
- No external libs.

### 2. FastAPI static mount — `app/main.py`

Add to `app/main.py` (near the existing `app.include_router(gear_router.router)` block):

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

# ... existing imports ...

# Conditional mount of the dev console. Tooling, not production.
_console_dir = Path(__file__).parent.parent.parent.parent / "tools" / "dev_console"
if _console_dir.exists():
    app.mount("/console", StaticFiles(directory=str(_console_dir), html=True), name="console")
```

Verify the path resolves correctly from `app/main.py` location. Adjust the parent count if needed (it should resolve to `<repo_root>/tools/dev_console/`).

The `if _console_dir.exists()` guard prevents the API from crashing if someone deletes the dev_console folder — it's a dev tool, not a hard dependency.

### 3. Test — `apps/api/tests/test_dev_console.py` (new)

```python
"""Dev console static-mount smoke test."""

from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_console_route_serves_html_when_dir_exists():
    """If tools/dev_console/index.html exists, /console/ serves it."""
    repo_root = Path(__file__).parent.parent.parent.parent
    console_dir = repo_root / "tools" / "dev_console"
    if not console_dir.exists():
        # Console wasn't built; skip rather than fail.
        import pytest
        pytest.skip("dev_console directory not present")

    response = client.get("/console/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"].lower()
    # Sanity check the content is actually our console:
    assert b"Blood Hunt Companion" in response.content
    assert b"Damage Simulator" in response.content


def test_console_returns_404_for_unknown_subpath():
    """/console/nonexistent → 404, not 200."""
    response = client.get("/console/nonexistent.txt")
    assert response.status_code == 404
```

### 4. README addition — one paragraph

In `README.md`, add a section (or augment an existing "Quickstart" / "How to use" section):

```markdown
## Interacting with the API (dev console)

After `make api`, open **http://localhost:8000/console/** in your browser. The dev console is a single-file static page that exposes the F1 Damage Simulator, F2 Roll Evaluator, and F4 Forge ROI endpoints with simple forms — no Next.js frontend required. It's a stopgap until the real `apps/web/` frontend lands.
```

If F4 hasn't landed yet at the time this prompt runs, just write "F1 Damage Simulator and F2 Roll Evaluator endpoints" and add F4 in the F4 PR's docs update.

---

## Lint / type / boot

- `ruff check apps/api` clean (only Python is linted; the HTML/CSS/JS isn't subject to ruff).
- `mypy --strict apps/api` clean.
- `make api` boots without errors.
- Smoke test: open `http://localhost:8000/console/` in a browser, fill the Damage Simulator form with `hero_id=squirrel_girl`, target `horde`, empty gear/traits/arcana, click submit. Should return a `SimulationResponse` with non-zero DPS.

---

## Things to double-check before declaring done

- All prior tests still pass.
- Phase 2 OCR fixture-skip gate still skips cleanly.
- No imports from `app/ocr/*` or `app/services/*` in the new code (the static mount only needs FastAPI's StaticFiles).
- The HTML file is genuinely self-contained — no `<link>` or `<script src=>` tags pointing at external resources.
- The `_console_dir` path resolves correctly. Print it once in a debug log to verify, then remove the print.
- Manual smoke test all three sections (or two if F4 isn't landed yet).
- `make lint` and `make test` both green.

---

## What I expect back from you

After your `§3.1` plan, execute. Then report:

(a) Final test count (passing / skipped) and confirmation `test_ocr_fixtures.py` still skips cleanly.
(b) Files created / modified — table or list.
(c) The commit message (single commit, imperative present tense).
(d) Anything you noticed not in the brief — particularly:
    - Whether F4 endpoint was present at the time you ran this (affects forge section behavior).
    - Any path-resolution edge case for the `_console_dir` mount.
    - Any place where the schema-paste-as-JSON UX felt awkward enough to merit a structured form (you can defer to a follow-up; do NOT build a structured form in this PR).
    - Browser compatibility caveats if any (e.g., if you used `<dialog>` or other newer HTML5 features that need fallback).
(e) The exact URL the user should open to verify.
(f) Push status — pushed to `origin/main`, or held locally pending user push.

If `make test`, `make lint`, or `make api` are not green, **do not declare done** — keep the task `in_progress` and surface the failure for triage.

---

## Phase 2 deferral statement (include in your commit message body, verbatim)

> Defers Phase 2 acceptance criterion: test_ocr_fixtures.py >=9/10 pass rate
> at TARGET_PASS_RATE=0.9. User fixture capture is at 3 of 10+. Code-side
> Phase 2 (persistence, calibration-free pipeline, tier dual strategy, slot
> detection) remains complete; only the user-gated accuracy gate is open.
> Adding stopgap dev console per Cowork's recommendation; not part of the
> planned apps/web/ Next.js frontend (Phase 3 deliverable per PROJECT.md sec 9).

---

## What this is NOT (recap)

- **Not** the planned Next.js frontend at `apps/web/`. That work is unaffected.
- **Not** a permanent UI. When the real frontend lands, this can be deleted with no migration.
- **Not** a public-facing tool. Same `localhost`-only posture as the rest of the app.
- **Not** a `.exe` / Tauri wrapper. That's V2 work per `PROJECT.md` §5.
- **Not** mobile-friendly. Desktop dev tool.

The point is to give the user something to interact with **today** — F1 + F2 (and F4 if landed) — without waiting on weeks of frontend scaffolding.
