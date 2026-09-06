# Third-party notices

## Forge Hammer / FoE Helper

The formulas and factual reward-table values used by this module were analyzed from FoE Helper 4.8.1.0, installed Chrome extension ID `bkagcmloachflbbkfmfiggipaelfamdf`, and from the earlier Forge Hammer 1.6.0 source lineage.

Relevant upstream files:

- `js/web/greatbuildings/js/greatbuildings.js` (`Rewards`, `GetBruttoCosts`, and `GetMaezen`)
- `js/web/part-calc/js/part-calc.js` (live construction reward handling)
- `js/web/technologies/js/technologies.js` (era identifiers)
- `js/web/_main/js/_main.js` (rounding helper)

The inspected source identifies the FoE Helper team and is licensed under the GNU Affero General Public License v3.0. Upstream: <https://github.com/mainIine/foe-helfer-extension>

This module re-expresses the observed algorithms and includes extracted factual game-data values; it does not bundle the extension itself.

## Contributor reward tables

FoE Helper intentionally relies on the live game response for medals and blueprints. The base offline target-level tables used to complete this analysis are normalized from the public Great Building pages at <https://foe.kwister.net/GB_list/>. The fetcher requests the site's unboosted view, retains medal P1 and five blueprint values per target level, and does not copy page presentation or code.

Those values and the derived medal-position rule were cross-checked against a local capture containing 1,134 `GreatBuildingsService.getConstruction` responses (5,670 ranked rewards). Blueprint availability for the very first levels was additionally checked against the Great Buildings table at <https://forgeofempires.fandom.com/wiki/Great_Buildings>.

Eight additional direct-game reward rows provide validation anchors above level 201: Château Frontenac target level 248, The Arc target level 214, and The Kraken target levels 234–239. Only sanitized building, era, target-level, and reward values are retained in the dataset; the raw captures are excluded from version control because they can contain player identifiers.

Stellar Age: Discovery medal values through target level 201 and 1,965 available medal P1 observations above level 201 were imported from FoE Helper's public Legendary Building API at <https://api.foe-helper.com/v1/LegendaryBuilding/>. The later observations provide complete level-301 medal tables for 17 eras, including Oceanic Future, and partial coverage for the other seven. API rows with an invalid duplicated neighbor value were rejected or resolved against a second Great Building from the same era. Reported P2–P5 values were validated against the module's normalized medal-position rule.

## Forge of Empires game metadata

Great Building names, eras, dimensions, foundation goods, and first-ten-level Forge Point requirements are sourced from a local capture of the game's `CityEntities` metadata. Forge of Empires is a trademark of InnoGames GmbH. This project is an independent analysis tool and is not affiliated with or endorsed by InnoGames.

## Level unlock costs

The rule requiring a full blueprint set for every level after 10 and the additional linear resource requirements of the three Saturn VI Gates, Stellar Warship, and Cosmic Catalyst were cross-checked against their public Great Building level tables at <https://forgeofempires.fandom.com/wiki/Great_Buildings>. Shattered Horizon Siphon's per-type goods, coin, supply, and medal requirements were cross-checked against the public level table at <https://foebeta.com/featured/great-buildings/?gb=shattered_horizon_siphon>.
