# GB Analysis

GB Analysis is a dependency-free local web module for exploring Forge of Empires Great Building upgrade, unlock cost, and contributor rewards through target level 301. Contributor rewards are sourced through level 201; above that, exact FP and medal observations are used wherever available and clearly identified fallback curves fill the remaining gaps.

The first feature answers four questions:

- How many Forge Points does a selected Great Building need for each level?
- How many Forge Points are required cumulatively through that level?
- What blueprints, goods, coins, supplies, medals, or special resources unlock that level?
- What are the P1–P5 Forge Point, medal, and blueprint rewards, with or without an Arc bonus?
- Which goods are required once, when the Great Building is founded?

The curve preview keeps unlike units on separate scales. Its cost selector includes FP,
aggregate goods, and every applicable non-blueprint resource; its reward selector plots
P1–P5 together for base FP, medals, or blueprints.

## Run it

```bash
npm run serve
```

Then open `http://localhost:8000`.

The serve command first creates `dist/`. CSS, JavaScript modules, and the JSON dataset
receive SHA-256 content fingerprints in their filenames. `index.html` is served with
`Cache-Control: no-cache`, while fingerprinted resources are served as immutable for one
year. A resource change therefore produces a new URL without requiring a forced browser
cache invalidation.

The local server saves dashboard inputs to `foe-gb-analysis-user-input.json` in the
operating system's temporary directory. Browser local storage provides a fallback when the
build is served as a plain static site. Use `scripts/serve_static.py --state-file PATH` to
select a different local state file.

To create the deployable static directory without starting the server:

```bash
npm run build
```

To run the formula and static-build tests:

```bash
npm test
```

## Data provenance and boundaries

The implementation was derived from the locally installed FoE Helper 4.8.1.0 extension (the current Forge Hammer source lineage):

- Upgrade FP: the first 10 values come from each game's `CityEntity`; later levels use `ceil(level_10_cost × 1.025^(level - 10))`, matching FoE Helper's `GetBruttoCosts`.
- Contributor FP: FoE Helper stores a P1 table by building era. P2–P5 reproduce its `GetMaezen` rounding sequence. Above level 201, exact API observations take precedence; missing P1 cells use the back-tested era curve `round5(eraFactor × (level^1.2 - 1) / 3.2)`.
- Contributor medals and blueprints: FoE Helper reads these from the live `GreatBuildingsService.getConstruction` response and applies the Arc multiplier to all three reward types. The sourced portion of the checked-in unboosted medal and blueprint tables covers target levels 1–201 and was cross-checked against 5,670 captured reward positions.
- Foundation goods and the first 10 upgrade costs come from the captured game `CityEntities` dataset.
- Every level after 10 requires a full blueprint set. The three Saturn VI Gates, Stellar Warship, Cosmic Catalyst, and Shattered Horizon Siphon also have building-specific resource unlock formulas; these are displayed separately from FP costs and contributor rewards.

The current dataset contains 49 Great Buildings, including the Stellar Age: Discovery building **Shattered Horizon Siphon**. Its 4×4 footprint, five lots of 5,200 foundation goods, and first-ten upgrade costs come from current game metadata. Its contributor FP table comes from FoE Helper 4.8.1.0; its level 1–201 medal data was imported from FoE Helper's public Legendary Building API. The API response was also used to validate every reported FP, medal, and blueprint position against the module's normalized tables.

FoE Helper does not bundle offline medal or blueprint reward tables, so the base tables for earlier eras are normalized from the unboosted public tables at [foe.kwister.net](https://foe.kwister.net/GB_list/) and checked against local game-response captures. Upgrade and level-unlock costs cover target levels 1–301 for every building. FP and medal rewards each use 1,965 exact later-level observations from FoE Helper's public Legendary Building API, giving complete exact coverage through level 301 for 17 era tables, including Oceanic Future and The Kraken. The exact FP rows correct 278 cells where the fallback was off by 5 FP. Fitted fallbacks are used only for the seven API coverage gaps; blueprint rewards above level 201 remain modeled. The dashboard identifies each modeled cell.

See [the Forge Hammer findings](docs/forge-hammer-findings.md) for the audited formulas and worked example, and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for source details.

## Rebuild the dataset

The checked-in dataset is self-contained. To refresh the base medal and blueprint source first (network required):

```bash
python3 scripts/fetch_contributor_rewards.py
```

Then import a saved FoE Helper `LegendaryBuilding/bulk` response for `X_StellarAgeDiscovery_Landmark1`:

```bash
python3 scripts/import_foe_helper_siphon.py \
  --response /path/to/siphon-levels-1-201.json
```

To refresh the exact FP and medal observations above level 201, pass the saved
bulk responses for the available Great Buildings, then rebuild the generated tables:

```bash
python3 scripts/import_foe_helper_fp_observations.py /path/to/gb-api-*.json
python3 scripts/import_foe_helper_medal_observations.py /path/to/gb-api-*.json
python3 scripts/derive_contributor_rewards.py
```

Derive the level 202–301 reward rows and update the checked-in application dataset:

```bash
python3 scripts/derive_contributor_rewards.py
```

Then rebuild the application dataset after an upstream source changes:

```bash
python3 scripts/build_dataset.py \
  --forge-hammer-source "/path/to/FoE Helper/js/web/greatbuildings/js/greatbuildings.js" \
  --city-entities "/path/to/great_buildings_entities.json" \
  --contributor-rewards data/contributor-rewards-source.json \
  --output data/gb-analysis.json
```

The extractors validate complete level coverage, five-position blueprint rows, era coverage, ten seed costs per building, building-specific unlock formulas, and agreement between overlapping FoE Helper/API reward data before writing.
