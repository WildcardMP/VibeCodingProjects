# Blood Hunt — Research Dossier

> **Audience:** Claude Code (and the project owner) building a personal companion app for Marvel Rivals' Blood Hunt PvE mode.
> **Owner profile:** Top-tier player. Cleared **Nightmare 160** (max difficulty). Ranked **6th on a Blood Hunt leaderboard**. Mains **Squirrel Girl** and **Moon Knight**.
> **Last updated:** April 27, 2026 (Season 7.5 live; mode runs 2026-04-23 → 2026-07-30 UTC).

This document is the source-of-truth knowledge dump. Every assumption the simulator and analysis tools depend on should be traceable back to a section here. When the game patches, update this file first, then the data layer.

---

## 1. Mode overview

Blood Hunt is the second PvE mode in Marvel Rivals (the first was Marvel Zombies). It is a **wave-based bullet-heaven hybrid with looter-RPG progression**, comparable in feel to *Vampire Survivors* and *Megabonk*. Players squad up (or solo with reduced enemy HP) and play one of six event-exclusive heroes through escalating phases that culminate in boss fights.

- **Available:** 2026-04-23 09:00 UTC → 2026-07-30 09:00 UTC (~98 days). Treat July 30 as the real deadline; the predecessor (Marvel Zombies) was extended once but planning around extensions is unsafe. ([Multiplayer First](https://mp1st.com/title-updates-and-patches/marvel-rivals-new-update-1-47-1-000-084-dracula-blood-hunt-mode))
- **Access:** Main menu → Playlist → Rivalry tab → Blood Hunt icon. ([GAMES.GG](https://games.gg/marvel-rivals/guides/marvel-rivals-how-to-play-blood-hunt-mode/))
- **Squad size:** 1–4. Solo runs reduce enemy and boss HP. ([Destructoid](https://www.destructoid.com/how-to-play-blood-hunt-mode-in-marvel-rivals/))
- **Hero duplicates allowed.** Four Squirrel Girls is a legitimate composition.

### 1.1 Difficulty ladder

| Tier | Bosses encountered | Notes |
|---|---|---|
| **Normal** | Capwolf | Single boss, gear farming starts here |
| **Hard** | Capwolf, Ratatoskr | Extended phase count |
| **Extreme** | Capwolf, Ratatoskr, Dracula, *Kingpin (hidden)* | Blood Crystal phase appears; Kingpin requires three sequential hidden objectives |
| **Nightmare 1–120+** | Full gauntlet | 5 phases (4 wave + 1 boss). Beating level N unlocks N+5. Scales HP and damage per level. NM 160 is the documented hard cap. |

Sources: [GAMES.GG](https://games.gg/marvel-rivals/guides/marvel-rivals-how-to-play-blood-hunt-mode/), [Beebom](https://beebom.com/marvel-rivals-blood-hunt-mode-rewards-how-to-play/).

### 1.2 Hidden Kingpin objectives (Extreme only)

Three steps, **in order**, in the same run:

1. **Phase 4** — destroy a barrier
2. **Phase 7** — destroy Bloodcut Buds
3. **Phase 12** — destroy Blood Crystals

Miss any and Kingpin is skipped. ([Beebom](https://beebom.com/marvel-rivals-blood-hunt-mode-rewards-how-to-play/))

### 1.3 Boss roster

| Boss | First appears | Key mechanics |
|---|---|---|
| **Capwolf** (werewolf Captain America) | Normal | Fast melee; can one-shot inattentive players |
| **Ratatoskr** | Hard | Adds + mobility threat |
| **Dracula** | Extreme | Blood Sacrifice gauge, ~3 min enrage timer, Sword phase, Crystal phase, light beam instakill |
| **Kingpin** (hidden) | Extreme (objectives) / NM | Cane Strike (immobilize on hit — dodge), AoE leap explosion (high damage, wide radius — keep distance) |

**Dracula deep-dive:**

- Each player has a **Blood Sacrifice** indicator above their head. Increases when Dracula hits you; determines how much HP he heals from his next siphon move. **Stay at range** to keep it low. ([reddit Dracula guide](https://www.reddit.com/r/marvelrivals/comments/1swsrvb/blood_hunt_extremely_quick_guide_to_fighting/))
- Around 66–75% HP: Dracula vanishes, summons swords + minions. **Destroy 5 swords**; minions are ignorable (and don't add Blood Sacrifice).
- Final phase: Dracula raises **two crystals near his throne** to fully heal. Destroy them and a **light beam** appears in the arena. If Dracula steps into the beam, he dies instantly.
- Hidden third crystal exists on the chandelier (visible only by chains).
- ~3-min boss timer; on expiration his attacks become lethal — coordinate or surrender to save resources.
- Jeff's hide-and-seek can interrupt his cloak phase (hitting him while cloaked makes him reappear).

---

## 2. Heroes

Six event-exclusive heroes. Each has its own independent level (max **60**), with **1 trait point per level**. Levels do **not** carry over between heroes — this is the single biggest community pain point ([reddit powerleveling](https://www.reddit.com/r/marvelrivals/comments/1sv8nph/blood_hunt_powerleveling_laziness_and_cowardice/)).

### 2.1 Tier list (community consensus, NM-pushing context)

| Tier | Hero | Role | Notes |
|---|---|---|---|
| **S+** | Squirrel Girl | Solo carry / sustained DPS | Best solo hero. Scales to NM 160 with the right build. |
| **S+** | Moon Knight | Burst boss-melter / hybrid | Two viable trees. Boss melt unmatched once Ankhs attach. |
| **S** | Jeff the Land Shark | Sustained DPS | Late bloomer; Overflowing Waters → Forked Stream is the path |
| **S** | Thor | Anchor / sustain | Most reliable solo; one per team is ideal |
| **A** | The Punisher | Boss specialist | Struggles vs swarms; rifle/shotgun build melts bosses |
| **B** | Blade | Hybrid | Dropped off vs Marvel Zombies; gun build still viable |

Sources: [GAMES.GG tier list](https://games.gg/marvel-rivals/guides/marvel-rivals-best-characters/), [marvelrivals.gg tier list](https://marvelrivals.gg/blood-hunt-tier-list-pve/), [Boostmatch](https://boostmatch.gg/blog/marvel-rivals/articles/marvel-rivals-blood-hunt-tier-list).

> **Owner focus:** Squirrel Girl and Moon Knight. The simulator's first-class heroes. Other four are second-class — data modeled but no UI optimization.

### 2.2 Squirrel Girl

**Trait tree structure:** three columns — General (purple), Burst Acorn (gold), Squirrel Friends (blue).

**Two viable builds, often combined:**

- **Burst Acorn (gold)** — primary attack scaling. Precision rate / precision damage are the headline stats.
- **Squirrel Friends (blue)** — the **Squirrel Storm** node spawns squirrels that latch onto enemies, applying continuous bite damage, slow, and **vulnerability** (bosses can stack up to 100 squirrels for huge multiplicative damage).

**Rank-1 build (NM 100–160 SOLO):** combine **gold + blue**. Key trait nodes:

| Node | Role | Notes |
|---|---|---|
| **Squirrel Storm** | (Blue, ≥1 pt) | Required to spawn Squirrel Friends |
| **Rodent Plague** | (Blue, max) | Squirrels apply slow + 45% vulnerability |
| **Jumbo Acorn** | (Blockade, 3 pts) | Blockade applies vulnerability — stacks with Rodent Plague to ~+282% damage taken in tested setups |
| **Natural Symbiosis** | (Blue/General) | Mammal Bond duration extension |
| **Rhythm of Nature** | (Blue/General) | Reduces Mammal Bond cooldown on damage dealt |
| **Cycle of Nature** | (General) | Every 20,000 damage dealt → Mammal Bond CD drops to 3s. Effectively instant reset at high NM |
| **Buddy Boost** | (General) | Reduces Squirrel Blockade cooldown — can drop to ~0 in NM scaling |

**Primary stats to chase:**
1. **Precision Rate** + **Precision Damage** (orange numbers — like crit but separate channel; legendary rolls observed at +8300% precision damage on a single piece)
2. **Total Output Boost / Damage Bonus**
3. **Mammal Bond duration** and **Squirrel Blockade cooldown reduction**
4. **HP %** (only enough to survive at current NM tier)

**Gameplay loop:**
1. Stay airborne in Mammal Bond (infinite tail jumps once Symbiosis + Rhythm chained)
2. Apply Squirrel Blockade to stack vulnerability → enemies glow purple
3. Spam Burst Acorns (precision shots)
4. On bosses, get all 100 Squirrel Friend stacks attached for max damage
5. Health regenerates from Mammal Bond drops + healing runes — effectively untouchable

Sources: [Rank 1 build video](https://www.youtube.com/watch?v=M_hmJqkdrFU), [NM 100+ solo guide](https://www.youtube.com/watch?v=fAbTC4a6wjQ), [reddit thread](https://www.reddit.com/r/marvelrivals/comments/1sv2zgs/squirrel_girl_blood_hunt_build/), [Boostmatch](https://boostmatch.gg/blog/marvel-rivals/articles/squirrel-girl-blood-hunt-build-guide-marvel-rivals).

### 2.3 Moon Knight

**Trait tree structure:** three columns — General (purple), **Phases of the Moon / Ankh (blue)**, **Fist of the Moon God / Melee (gold)**.

**Two distinct builds — pick one:**

#### 2.3.1 Blue (Ankh) — boss melter

**Concept:** Throw Ankhs that attach to enemies (including bosses). Crescent Darts bounce between Ankhs for massive multi-hit damage. Increase Ankh count, bounce frequency, and bounce-per-Ankh.

**Key nodes:**
- Increase Ankh count on the field
- Increase bounce frequency
- **Attach Ankhs to bosses** (the killer node — bosses cannot escape bounce range)

**Stats:** Total Output Boost ≫ Precision Damage. Community A/B (PeaceDuck vs. Luke) showed **Total Output dominant over Precision** at top end. ([reddit stat analysis](https://www.reddit.com/r/marvelrivals/comments/1svkmki/alright_i_found_it_the_best_stat_in_the_pve/))

**Gear focus:** **Scepter of Rites** weapon, **Pendant of Oshtur** accessory.

**Why this melts Dracula:** Once Ankhs are attached to him, the Vampire King cannot escape Crescent Dart bounce range during phase transitions. ([Dracula Moon Knight guide](https://www.youtube.com/watch?v=r4nlmaUpcQA))

#### 2.3.2 Gold (Melee Spin Kick) — hybrid solo

**Concept:** Override darts with melee. **Lunar Tide** puts Ankh on your head — pulls enemies in. **Full Moon Spin** roundhouse kick = primary kill move. Walking AoE bomb.

**Key nodes (max 3 stacks each):**
- **Fist of Eclipse** (3) — melee override
- **Full Moon Spin** (3) — primary damage source
- **Lunar Momentum** (3) — attack speed
- **Lunar Tide** — Ankh on head, pulls enemies
- **Cooldown Reduction** (over Primary Attack Speed)
- **SKIP:** Fist of Konchu, Moon God's Chosen (ult-related, irrelevant for this build)
- **SKIP:** Ankh Siphon (ult charge — not used)
- **Buy:** Close Quarters (+20% close-range damage), Boss Hunter, Moonlight Healing
- **Stats:** Ability Damage Bonus, **Close Quarters Damage** (S-tier roll observed at 830%)

**Mobility tech:** Look at floor → grappling hook = ejector seat straight up.

**NM 70 solo confirmed clear** with this build. ([True Vanguard NM 70 guide](https://www.youtube.com/watch?v=LzR4cAKQ1QU))

**Gear focus:** **Alchemy Amulet** with S-tier Close Quarters Damage extended effect. Legendary chest piece variants:
- 6 heal charges (vs. base 3), or
- ~70% heal cooldown reduction (S-tier variant)

### 2.4 Other heroes (lower priority — model data, deprioritize UI)

- **Jeff the Land Shark** — Overflowing Waters trait focus, exclusive gear first; Forked Stream unlocks splits spit into 3 streams. NM 120 reachable. Splash builds for early NM, hide-and-seek for endgame. Boss DPS weakness mid-late. ([Boostmatch](https://boostmatch.gg/blog/marvel-rivals/articles/jeff-land-shark-blood-hunt-build-guide-marvel-rivals))
- **Thor** — Elderwood Haft weapon (Storm Surge scaling), Cosmic Cape. Can clear NM 160. ([all-heroes guide](https://www.youtube.com/watch?v=p9TlCjs9O00))
- **The Punisher** — Rifle (Fatal Pursuit, +damage per meter) or Shotgun build. Boss specialist; struggles solo on swarms. NM 90 boss kill in ~180B damage observed. ([Punisher build](https://www.youtube.com/watch?v=jMApGy2iGwY)) Phoenix Force exclusive for shotgun. Run with the team for swarm cover.
- **Blade** — Gun build w/ Exorcism Rounds + Reap. Lifesteal scaling; Purging Bladedance + Silver Soulbreaker traits. ([Boostmatch Blade guide](https://boostmatch.gg/blog/marvel-rivals/articles/blade-blood-hunt-build-guide-marvel-rivals)) Dropped off vs. Marvel Zombies.

---

## 3. Gear system

**Four gear slots per hero (independent inventories):**
- **Weapon** — primary damage / attack-speed / ability scaling
- **Armor** — HP, damage reduction, CC resistance (and importantly heal charges/CDR on legendary)
- **Accessory** — cooldowns, mobility, energy/utility
- **Exclusive** — hero-specific signature buffs

### 3.1 Rarity → extended effect count

In-game vocabulary (confirmed against user screenshots 2026-04-27 — earlier drafts of this doc used the wrong words):

| Rarity | Color | Extended Effects | Notes |
|---|---|---|---|
| Normal | White | 0 | Base stats only — smelt fodder |
| Advanced | Green | 1 | Smelt fodder past early NM |
| Rare | Blue | 2 | Bridge tier |
| Epic | Purple | 3 | Required for early NM |
| Legendary | Gold | up to 5 | Required for NM 50+; max stat rolls |

**Up to 5 extended effects** on a Legendary, plus 1+ base effects (e.g. armor shows BOTH `Health` and `Armor Value` under BASE EFFECT). The tooltip's overall **rating** integer at the top (e.g. 7086 on a high-roll legendary) summarises the magnitudes across all five.

Sources: [Blood Hunt wiki gear page](https://www.marvelrivalsbloodhunt.wiki/gear/Marvel-Rivals-Blood-Hunt-gear), [beginner guide video](https://www.youtube.com/watch?v=RGWbEsb-yZo), user-captured tooltip screenshots (Moon Knight Runic Armor, rating 7086).

### 3.2 Extended effect tiers (D / C / B / A / S)

**Each extended effect has its own internal tier**, separate from the gear's overall rarity. The tier determines the **magnitude of the rolled value**. Same stat name, very different numbers (table shows the observed end-points; C/A fall between B and S in a smooth ramp):

| Stat | D | C | B | A | S |
|---|---|---|---|---|---|
| Bonus Damage vs. Close-Range | 129% | ~200% | 250% | ~500% | 830% (Alchemy Amulet) |
| Precision Damage | — | ~1000% | ~3000% | ~5000% | 8300% (legendary) |

C and A values are interpolated estimates pending FModel extraction of `DT_GearStats` tier-range tables — datamined min/max will replace the `~` figures.

**Rating system:** the all-heroes guide references a max **rating of 7,500** = 5 extended effects, all at S rank. This is the theoretical legendary ceiling. ([all-heroes build guide](https://www.youtube.com/watch?v=p9TlCjs9O00))

> **Implication for the simulator:** every extended effect needs `(stat_name, tier_letter, rolled_value, rolled_value_max_for_tier)` to be modeled. Tier is what really matters; rolled_value is the noise within tier.

### 3.3 Known stat name catalog (from primary sources)

This is the **stat schema** the OCR parser must recognize. Treat as canonical and extend as new ones are observed in-game.

**Universal damage stats:**
- Total Output Boost
- (Total) Damage Bonus
- Ability Damage Bonus
- Primary (Damage) Bonus / Primary Damage Bonus
- Boss Damage / Bonus Damage vs. Bosses
- Bonus Damage vs. Close-Range Enemies
- Bonus Damage vs. Healthy Enemies *(community-flagged as worst stat — avoid)*
- Critical Hit Rate
- Critical Damage
- Precision Rate
- Precision Damage
- Multi-Trajectory *(specific weapons)*

**Survivability:**
- Health (flat)
- Health (%)
- Armor Value
- Block Rate
- Health Restored (per shot fired / per kill / etc.)

**Utility:**
- Cooldown Reduction (general)
- Rune Cooldown Reduction *(armor S-tier, very strong)*
- Heal Charges *(armor — base 3, +1 per charge upgrade, legendary up to 6)*
- Attack Speed
- Extra Ammo Capacity
- Ultimate Charge / Ultimate Boost
- Drop Rate (Arcana-only?)
- Healing Charges Cooldown Reduction

**Hero / weapon-specific (subset):**
- Squirrel Girl: Mammal Bond Duration, Squirrel Blockade Cooldown, Squirrel Friends count, Vulnerability application %
- Moon Knight: Ankh count, Ankh bounce frequency, Crescent Dart bounce count, Spin Kick damage, Close Quarters Damage
- Punisher: Fatal Pursuit (% per meter), Extended Magazine, Ricochet
- Jeff: Gliding firing interval reduction, Splash radius
- Thor: Storm Surge scaling
- Blade: Exorcism Rounds buffs, Lifesteal

> **OCR note:** stat names are stable strings across runs. Build a fuzzy-match table; OCR errors on exact characters are recoverable.

### 3.4 Stat priority by build (community consensus)

1. **Total Output Boost** — universally best. Primary target on every gear piece.
2. **Total Damage Bonus** — second-best generic stat.
3. **Critical Damage** — only invest if you have crit rate (gear or trait).
4. **Precision Damage** — only invest if you have precision rate. Squirrel Girl exception: precision can dominate due to slingshot natural precision rate.
5. **Boss Damage** — high value if your build is boss-focused (Punisher, Moon Knight Ankh, Squirrel Girl on bosses).
6. **Damage vs. Close-Range** — Moon Knight melee, Punisher shotgun.
7. **Cooldown Reduction (Rune CDR especially)** — armor S-tier, enables damage cycling.

**Avoid:**
- **Damage vs. Healthy Enemies** (XJ9 calls it "the most worthless stat" — wears off too fast). ([XJ9 guide](https://www.youtube.com/watch?v=8Q5JzVPnmZs))
- **Ammo Capacity at S-tier** ("awful") — overkill, wasted roll.
- **HP %** beyond survival threshold for current NM tier.

**Crucial finding (NM 160 context):** Total Output Boost beats crit/precision in raw consistency. Crits and precision happen less often but hit harder when they do — but the math favors flat output unless you can stack precision rate to absurd levels. ([reddit stat analysis](https://www.reddit.com/r/marvelrivals/comments/1svkmki/alright_i_found_it_the_best_stat_in_the_pve/))

### 3.5 Drop sources

- **Standard enemies** drop low-level gear during runs.
- **Bosses** drop higher-level gear.
- **Phase transitions** spawn elite enemies that drop guaranteed loot — pounce on them.
- **Legendary drops** spawn a visible spire of light. Hard to miss.
- **Legendaries effectively don't drop until NM 20–25**; frequency increases with NM tier.
- **Some "legendary" drops are actually currency tokens**, not gear — confusing, but expected.

### 3.6 Gear levels

- Drop level scales with run difficulty: NM 5 ≈ level 8 drops, NM 30 ≈ level 30 drops, NM 160 ≈ level 60 drops (cap).
- **Level cap = hero level cap = 60.** Cannot equip gear above your hero level.
- Forge cap = your current hero level.

---

## 4. Forge system

The Forge is RNG-mitigation. Smelt anything you don't need into **Uru Shards**, then craft new gear at chosen hero/slot/level.

### 4.1 Workflow

1. **Lock** any gear you want to keep (the "Select All" smelt option will eat it otherwise — community pain point).
2. **Filter** by rarity (e.g., All ≤ Blue) → Select All → Smelt → Uru Shards.
3. Open Forge → click center shard → choose **hero** + **slot** preset.
4. Choose level (always pick **highest available** — equals current hero level).
5. Forge in **stacks of 10** for efficient legendary hunting.

### 4.2 Forge math (community-observed)

- **~1 in 10 forged at max level → Legendary** (huge variance: 0–3 per stack of 10 observed).
- **Higher hero level → better Epic/Legendary odds** (Jeff lvl 32 ≫ fresh Jeff).
- **Stack of 10 at level 60 ≈ 200,000 Uru Shards** (per Moon Knight NM 70 guide).
- **NM 70 unlock:** two new Arcanas — non-boss KO drop rate + **current-difficulty best gear drop rate** (the latter shifts more drops to top level).

> **Implication for the Forge ROI feature:** model expected legendary count = `forge_count × P(Legendary | hero_level)`. Use observed 10% as default; let user override based on their patch-current observations.

### 4.3 Smelt value

Uru Shards per item depends on **level × rarity**. Low-tier items = small returns; high-level greens/blues are the bulk of shard income at endgame.

### 4.4 Cross-hero crafting

Smelt one hero's gear → use shards to forge for a different hero. Useful for funneling into your main.

---

## 5. Arcana system

**Two Arcana systems exist** — easy to confuse:

### 5.1 Arcana (meta-progression — Arcane Realm)

Permanent, persistent buffs across all your runs. Spend Arcana points earned at level-ups in the **Arcane Realm** menu.

**Four scrolls (current confirmed list — partial):**

| Scroll | Unlock | Effect |
|---|---|---|
| **Scroll of Conquest** | Normal | Total Output Boost |
| **Scroll of Immortality** | Normal | Health |
| **Scroll of Blessing** | Clear NM 70 | TBC (likely drop-rate or non-boss KO drop) |
| **Scroll of Midas** | Clear NM 70 | TBC (likely current-difficulty best gear drop rate) |

The two NM 70 unlocks are the ones that shift drop rates ~+20% according to the legendary drop guide. ([legendary drops guide](https://www.youtube.com/watch?v=lL-nUbE9ceM), [Beebom](https://beebom.com/marvel-rivals-blood-hunt-mode-rewards-how-to-play/))

**Recommended priority:**
1. Max **Scroll of Conquest** (Total Output Boost — best stat in the game)
2. Max **Scroll of Immortality** (HP)
3. Max **Skull of Immortality** (Punisher build context)
4. Drop-rate scrolls last (until you're farming legendaries seriously)

> **Note on naming:** "Skull of Immortality" mentioned in the Punisher build video may be a separate Arcana node or a renaming. **TODO:** confirm in-game once we have visual access.

### 5.2 Arcana Points (in-run)

Earned mid-match by clearing waves. Spend at the **Arcana Store** between phases. Three random options offered each visit. Choose Arcana that synergizes with your gear's stat focus (e.g., crit rate Arcana if crit damage is your gear focus).

> **Implication for the simulator:** Arcane Realm scrolls are **persistent multiplicative modifiers** in the damage formula. In-run Arcana pickups are **stochastic** — model as "expected value of ~3-4 picks per run from a pool of ~N options." Phase 2 feature.

---

## 6. Damage model (theorycraft scaffold for the simulator)

This is the core math the simulator must implement. Treat as a **best-effort first pass** — refine as we observe in-game numbers and community theorycrafting.

### 6.1 Generic damage formula

```
damage_per_hit =
    ability_base_damage(hero, ability, ability_rank)
  × (1 + Total_Damage_Bonus_sum)
  × (1 + Total_Output_Boost_sum)
  × (1 + Ability_Damage_Bonus_if_applicable)
  × (1 + Primary_Damage_Bonus_if_applicable)
  × (1 + Boss_Damage_Bonus_if_target_is_boss)
  × (1 + Close_Range_Bonus_if_target_in_range)
  × (1 + Arcana_multiplier)
  × precision_multiplier(precision_rate, precision_damage)
  × crit_multiplier(crit_rate, crit_damage)
```

Where:

```
precision_multiplier = 1 + precision_rate × precision_damage
crit_multiplier = 1 + crit_rate × crit_damage
```

(These two channels appear independent — precision shows orange numbers, crit shows yellow; both can stack, but rolls are scarce so only one dominates per build.)

### 6.2 DPS

```
dps =
    damage_per_hit
  × hits_per_second(attack_speed, weapon_base_rate)
  × uptime_modifier(cooldowns, ammo, reload)
  × multi_target_multiplier(bounces, AoE, summons)
```

For multi-bounce kits (Moon Knight Ankh, Squirrel Girl Friends), `multi_target_multiplier` is the dominant term — model it as a function of `(ankh_count, bounces_per_ankh, target_count_in_range)`.

### 6.3 Boss-specific multipliers

For boss damage, layer:

```
boss_damage = generic_damage_per_hit
            × (1 + Boss_Damage_Bonus)
            × ankh_attached_multiplier      # MK only: every dart bounces back from boss
            × squirrel_friends_stack(n)     # SG only: up to 100 stacks of vulnerability + bite damage
```

`ankh_attached_multiplier` and `squirrel_friends_stack` are the differentiators that put Squirrel Girl + Moon Knight in S+. Get them right and the simulator predicts top-tier output; get them wrong and it underestimates by an order of magnitude.

### 6.4 Effective HP (survivability)

```
EHP = HP × (1 + HP_percent_bonus) / (1 - damage_reduction_from_armor)
heal_per_minute = heal_amount × charges / cooldown × (1 + cdr_bonus)
```

For NM 160, `EHP × heal_per_minute` is the survival check. Squirrel Girl effectively passes infinitely thanks to Mammal Bond regen + 4,000 extra HP legendary armor + 3 extra healing runes.

### 6.5 Calibration TODOs

- [ ] Get base ability damage values per hero (FModel datatables — see DATA_PIPELINE.md)
- [ ] Confirm precision/crit channel independence
- [ ] Confirm multiplicative vs. additive stacking for "Total Output Boost" + "Total Damage Bonus"
- [ ] Get Ankh bounce-per-second base rate
- [ ] Get Squirrel Friend bite damage scaling per stack
- [ ] Confirm Arcana Realm Conquest scroll value per level

These calibration values are the difference between a useful simulator and a toy. **Treat extracting them from FModel as a critical-path task.**

---

## 7. Reward track (motivation — used for run prioritization)

For tracking what's left to chase:

| Milestone | Reward |
|---|---|
| Clear Normal first time | 100 Units, King in Exile Gallery Card |
| Clear Hard first time | 100 Unstable Molecules, Squirrel Gone Wild Card |
| Clear Extreme first time | 100 Units, Hunting Season Card |
| Defeat hidden Kingpin (Extreme) | Kingpin Dethroned Accessory, Animal Instinct Card |
| Clear NM 5/10/15/20/25/30/35/40/45/50/55/60/65/70/80 | Various moods, sprays, units, molecules, Kingpin Trophy Shards |
| Clear NM 100 | Bane of all Evil Title + 10 Trophy Shards |
| Clear NM 120 | 10 Trophy Shards |
| As Punisher, NM 40 | Vampiric Vengeance Emoji |
| As Punisher, NM 70 | Fearless Executioner Title |
| As Squirrel Girl, NM 40 | Back Off, Bloodsucker! Emoji |
| As Squirrel Girl, NM 70 | Ravenous Rodent Title |
| As Jeff, NM 70 | Jeff the Night Shark Title |
| Defeat 5K / 10K / 15K / 20K / 30K / 40K enemies | Currencies, Dracula's Demise Spray, Blood Hunt Nameplate |
| Collect 100 Kingpin Dethroned Trophy Shards | Kingpin Dethroned Trophy Accessory |

> **Owner status note:** at NM 160 with #6 leaderboard, all Nightmare clears are likely done. Remaining: hero-specific titles for non-mains (Jeff Night Shark, Punisher titles), 40K kills (if not done), Trophy Shard collection.

---

## 8. Data acquisition feasibility (summary — full details in DATA_PIPELINE.md)

| Source | Available? | Useful for |
|---|---|---|
| **Official NetEase API** | ❌ Does not exist publicly | — |
| **Community APIs** (marvelrivalsapi.com, MR(API), tracker.gg) | ⚠️ Player profile + match history only — **no Blood Hunt / gear / trait data** | Rank/MMR display only (low value for this app) |
| **Overwolf Live Game Data** | ⚠️ Live PvP match info + cooldowns + roster — **no PvE, no gear** | Possibly future overlay; not core |
| **Memory injection / process hooks** | ❌ Banned by NetEase (Blitz precedent) | — |
| **FModel + Repak Rivals (game files)** | ✅ **Yes — UE5.3, AES keys public** | All static numerical data: ability scaling, trait multipliers, gear stat ranges, Arcana effects |
| **OCR on screen** | ✅ **Yes — proven approach (D2R Loot Reader, etc.)** | Personal inventory ingest, run logging |
| **Replay video files** | ⚠️ Stored as video at `%LOCALAPPDATA%\Marvel\Saved\VideoRecords` | Post-hoc OCR review, lower priority |

**Verdict:** **OCR (personal data) + FModel (static data) = the architecture.** This is detailed in DATA_PIPELINE.md.

---

## 9. Source index

Every claim above traces to one of these. Cited inline.

**Primary mode info:**
- [Multiplayer First — patch notes](https://mp1st.com/title-updates-and-patches/marvel-rivals-new-update-1-47-1-000-084-dracula-blood-hunt-mode)
- [Destructoid — overview](https://www.destructoid.com/how-to-play-blood-hunt-mode-in-marvel-rivals/)
- [GAMES.GG — how to play](https://games.gg/marvel-rivals/guides/marvel-rivals-how-to-play-blood-hunt-mode/)
- [Beebom — full guide](https://beebom.com/marvel-rivals-blood-hunt-mode-rewards-how-to-play/)
- [Marvel Rivals Wiki (Fandom) — Blood Hunt](https://marvelrivals.fandom.com/wiki/Blood_Hunt)
- [Marvel Rivals Blood Hunt wiki](https://www.marvelrivalsbloodhunt.wiki)

**Tier lists / meta:**
- [GAMES.GG tier list](https://games.gg/marvel-rivals/guides/marvel-rivals-best-characters/)
- [marvelrivals.gg tier list](https://marvelrivals.gg/blood-hunt-tier-list-pve/)
- [Marvel Rivals Blood Hunt wiki tier list](https://www.marvelrivalsbloodhunt.wiki/tier-list/Marvel-Rivals-Blood-Hunt-best-hero-tier-list)
- [Boostmatch tier list](https://boostmatch.gg/blog/marvel-rivals/articles/marvel-rivals-blood-hunt-tier-list)

**Hero builds:**
- Squirrel Girl: [Rank 1 build](https://www.youtube.com/watch?v=M_hmJqkdrFU), [NM 100+ solo](https://www.youtube.com/watch?v=fAbTC4a6wjQ), [NM 160 build](https://www.youtube.com/watch?v=Pj7m4loe6GY), [reddit thread](https://www.reddit.com/r/marvelrivals/comments/1sv2zgs/squirrel_girl_blood_hunt_build/), [Boostmatch SG](https://boostmatch.gg/blog/marvel-rivals/articles/squirrel-girl-blood-hunt-build-guide-marvel-rivals)
- Moon Knight: [Dracula melt guide](https://www.youtube.com/watch?v=r4nlmaUpcQA), [True Vanguard NM 70 melee](https://www.youtube.com/watch?v=LzR4cAKQ1QU), [reddit builds](https://www.reddit.com/r/marvelrivals/comments/1sun9gj/moon_knight_blood_hunt_builds/), [stat priority finding](https://www.reddit.com/r/marvelrivals/comments/1svkmki/alright_i_found_it_the_best_stat_in_the_pve/)
- All-heroes: [build guide for all 6](https://www.youtube.com/watch?v=p9TlCjs9O00), [XJ9 stat priority](https://www.youtube.com/watch?v=8Q5JzVPnmZs)
- Punisher: [boss destroyer build](https://www.youtube.com/watch?v=jMApGy2iGwY), [reddit Punisher tips](https://www.reddit.com/r/marvelrivals/comments/1sunc8y/any_tips_for_bloodhunt_as_high_lvl_punisher/)
- Blade: [Boostmatch Blade](https://boostmatch.gg/blog/marvel-rivals/articles/blade-blood-hunt-build-guide-marvel-rivals), [reddit Blade build](https://www.reddit.com/r/marvelrivals/comments/1subs8l/blood_hunt_best_blade_build/)
- Jeff: [Boostmatch Jeff](https://boostmatch.gg/blog/marvel-rivals/articles/jeff-land-shark-blood-hunt-build-guide-marvel-rivals)

**Systems deep-dives:**
- [Gear & Forge wiki page](https://www.marvelrivalsbloodhunt.wiki/gear/Marvel-Rivals-Blood-Hunt-gear)
- [Beginner's complete guide video](https://www.youtube.com/watch?v=RGWbEsb-yZo)
- [Complete PvE guide](https://www.youtube.com/watch?v=z3jByMusIoQ)
- [Legendary drops guide](https://www.youtube.com/watch?v=lL-nUbE9ceM)
- [All Things How — bosses & rewards](https://allthings.how/marvel-rivals-blood-hunt-how-to-play-bosses-and-rewards/)

**Boss mechanics:**
- [Dracula reddit guide](https://www.reddit.com/r/marvelrivals/comments/1swsrvb/blood_hunt_extremely_quick_guide_to_fighting/)
- [Voice line / interaction compilation](https://www.youtube.com/watch?v=wmTfkaRatp0)

**Powerleveling / progression:**
- [reddit powerleveling guide](https://www.reddit.com/r/marvelrivals/comments/1sv8nph/blood_hunt_powerleveling_laziness_and_cowardice/)

**Data feasibility (cited in DATA_PIPELINE.md):**
- [Overwolf Marvel Rivals API](https://dev.overwolf.com/ow-native/live-game-data-gep/supported-games/marvel-rivals)
- [marvelrivalsapi.com docs](https://docs.marvelrivalsapi.com)
- [marvelrivalsapi.com player endpoint](https://docs.marvelrivalsapi.com/player-stats-19312751e0)
- [NetEase Blitz ban statement](https://marvelrivals.gg/marvel-rivals-bans-third-party-plugins/)
- [Polygon — datamining culture](https://www.polygon.com/gaming/557881/marvel-rivals-data-mining-overwatch-code/)
- [Repak Rivals tool](https://www.nexusmods.com/marvelrivals/mods/1717)
- [FModel general extraction tutorial](https://www.youtube.com/watch?v=OWbWgjl4zuI)
- [picarica modding guide](https://github.com/picarica/Marvel-modding-guide)
- [d2r-loot-reader (OCR pattern reference)](https://libraries.io/pypi/d2r-loot-reader)

---

## 10. Open questions / TODOs

These need resolution before V1 ships. Most require in-game observation, FModel extraction, or owner confirmation.

- [ ] Confirm exact damage formula stacking (multiplicative vs. additive) per stat category
- [ ] Confirm Scroll of Blessing and Scroll of Midas exact effects
- [ ] Confirm "Skull of Immortality" — is it an Arcana or a renamed scroll?
- [ ] Pull base ability damage values for SG and MK from FModel
- [ ] Pull trait node multipliers from FModel
- [ ] Pull gear extended-effect tier value ranges (D/C/B/A/S min-max per stat) from FModel
- [ ] Confirm rated / rating system — is "max rating 7,500" a real in-game number or community-derived?
- [ ] Confirm legendary drop rate at hero level 60 (community estimate: ~10% per craft)
- [ ] Confirm Mammal Bond infinite uptime requirements (Cycle of Nature 20K dmg threshold)
- [ ] Catalog every Arcana scroll's per-level value
- [ ] Owner-specific: list all gear pieces the owner currently uses for Squirrel Girl + Moon Knight (will be auto-captured by OCR ingest at V1)
