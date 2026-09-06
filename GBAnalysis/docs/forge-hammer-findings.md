# Forge Hammer source findings

Analyzed extension: FoE Helper 4.8.1.0 (`bkagcmloachflbbkfmfiggipaelfamdf`), the current source lineage of the earlier Forge Hammer extension.

This note records the source behavior reproduced by GB Analysis. Line numbers refer to the inspected 4.8.1.0 installation and may move in later releases.

## Upgrade Forge Point cost

Source: `js/web/greatbuildings/js/greatbuildings.js`, `GetBruttoCosts` (around line 952).

FoE Helper accepts a zero-based level index. GB Analysis exposes the corresponding one-based target level to the user.

For target levels 1–10:

```text
cost(level) = CityEntity.strategy_points_for_upgrade[level - 1]
```

For target levels 11 and above:

```text
cost(level) = ceil(level_10_cost × 1.025^(level - 10))
```

The source applies the exponential formula directly to the level-10 seed every time; it does not repeatedly grow an already-rounded previous level.

## Contributor Forge Point rewards

Sources:

- `js/web/greatbuildings/js/greatbuildings.js`, `Rewards` (beginning around line 44)
- `js/web/greatbuildings/js/greatbuildings.js`, `GetMaezen` (around line 999)
- `js/web/part-calc/js/part-calc.js`, contribution event handling (around line 690)

FoE Helper bundles a P1 array for each numeric era. A contribution event at target level `N` uses array entry `N - 1`.

P2 through P5 are not stored separately. They are generated recursively from the immediately previous position:

```text
P1 = era reward table[level - 1]
P2 = round(P1 / 2 / 5) × 5
P3 = round(P2 / 3 / 5) × 5
P4 = round(P3 / 4 / 5) × 5
P5 = round(P4 / 5 / 5) × 5
```

FoE Helper's rounding helper adds a small epsilon before JavaScript `Math.round`. For each position, an Arc bonus is applied after the nearest-five base reward is calculated:

```text
adjusted reward = round(base reward × (1 + Arc bonus / 100))
```

It supports either one Arc percentage for all positions or a different percentage for each position. The current GB Analysis UI exposes one shared percentage; the core function supports both forms.

## Worked verification: The Arc, target level 80

The Arc's captured level-10 cost is 970 FP.

```text
ceil(970 × 1.025^70) = 5,464 FP
```

FoE Helper's Future Era P1 entry for target level 80 is 1,375 FP. Its recursive base positions are:

```text
[1,375, 690, 230, 60, 10]
```

At a 90% Arc bonus, the displayed rewards are:

```text
[2,613, 1,311, 437, 114, 19]
```

These values are covered by automated tests and were also verified in the browser-rendered module.

## Medals and blueprints

Source: `js/web/part-calc/js/part-calc.js` (around lines 690–711).

For a building currently opened in the game, FoE Helper reads three reward fields from the live construction response:

- `reward.strategy_point_amount`
- `reward.resources.medals`
- `reward.blueprints`

FoE Helper multiplies each of these three values by the contributor's Arc factor and runs the result through its rounding helper. Its future-level approximation reconstructs only FP and explicitly fills medals and blueprints with zero, so those zeros are placeholders rather than real rewards.

GB Analysis supplements that missing offline data with unboosted contribution tables through target level 201. The normalized model is:

```text
medals = [P1, round(P1 / 2), round(P1 / 4), round(P1 / 10), round(P1 / 20)]
blueprints = five explicit values indexed by target level
adjusted value = round(base value × (1 + Arc bonus / 100))
```

The medal rule and blueprint table were checked against 5,670 reward positions from 1,134 captured `GreatBuildingsService.getConstruction` responses. This includes positions whose FP reward is zero but which still award medals or blueprints—a case hidden by some public tables.

## Derived reward coverage through level 301

Levels 1–201 remain the sourced values. Levels 202–301 combine exact medal observations with three fallback reward families:

```text
FP P1 = round-to-nearest-5(era factor × (level^1.2 - 1) / 3.2)
era factor = era id + 9; No Age uses 14

medal P1 = exact API observation when available
medal P1 fallback = round(era scale × (level^1.200964 - 1))
blueprint P1–P5 = round(position scale × level^0.8)
```

Each medal era scale and each blueprint position scale is a least-squares fit over the sourced values. The fallback medal exponent minimizes absolute error across all available API observations above level 201. P2–P5 FP and medals continue to use the rules above; they are not fitted independently.

The FP equation was tested against every sourced level 11–201 value: all predictions were within 5 FP. The same rolling test reproduced 94% of blueprint cells exactly and every cell within one blueprint. The UI labels uncaptured levels 202–301 as modeled.

The direct captures are Château Frontenac target level 248, The Arc target level 214, and The Kraken target levels 234–239. Their available FP and blueprint values exactly match the existing formulas, and every captured P2–P5 medal value exactly matches the rounded P1 fractions.

The medal sequence has discrete table steps that a smooth power curve cannot reproduce exactly. Kraken target level 236 demonstrates this: its exact P1 value is 194,387, while the best smooth fallback still misses it by 31 medals. The dashboard therefore uses 1,965 exact later-level FoE Helper API observations instead of treating those steps as curve noise. Seventeen era tables now have exact medal coverage through level 301; seven eras retain explicitly marked gaps. Across the observed later rows, the fallback has 9.35 mean absolute error and a 103-medal maximum error, which is why it is never presented as exact.

The source contained one isolated missing medal value for Future Era target level 196. FoE Helper's public Legendary Building response supplies 102,874 medals, which is stored as a documented correction before the medal curve is fitted.

## Shattered Horizon Siphon and level-201 coverage

FoE Helper 4.8.1.0 adds numeric era 24 (`StellarAgeDiscovery`) and a P1 FP table for the Shattered Horizon Siphon. The source comments identify only levels 210, 216, and 242–243 as formula estimates, so its entries through target level 201 are live-derived values.

The public FoE Helper `LegendaryBuilding/bulk` response for `X_StellarAgeDiscovery_Landmark1` supplies construction cost and contributor FP, medals, and blueprints for every target level from 1 through 201. The import validates all API-reported positions against the recursive FP rule, medal fractions, and explicit blueprint table. At target level 201, the unboosted values are:

```text
upgrade FP = 1,623,768
cumulative FP = 66,051,010
FP P1–P5 = [5,975, 2,990, 995, 250, 50]
medals P1–P5 = [578,833, 289,417, 144,708, 57,883, 28,942]
blueprints P1–P5 = [32, 23, 18, 15, 12]
```

The newer helper also fills the earlier Industrial Age and Space Age Venus FP gaps present in Forge Hammer 1.6.0. The checked-in dataset has sourced FP, medal, and blueprint coverage through target level 201 for all 49 Great Buildings, exact later medal observations where available, and a labeled fallback extension through target level 301.
