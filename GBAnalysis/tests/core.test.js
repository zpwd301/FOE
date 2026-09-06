import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  applyArcBonus,
  arcBonusForLevel,
  arcLevelForBonus,
  buildBaseRewardSeries,
  baseMedalRewards,
  basePositionRewards,
  buildLevelRows,
  buildRageAnalysis,
  buildUpgradeCostSeries,
  rewardsForLevel,
  unlockCostsForLevel,
  upgradeCost,
} from "../src/core.js";

const ARC_FIRST_TEN = [70, 110, 200, 290, 400, 510, 620, 740, 860, 970];

test("Forge Hammer upgrade formula preserves levels 1–10 and grows from level 10", () => {
  assert.equal(upgradeCost(ARC_FIRST_TEN, 1), 70);
  assert.equal(upgradeCost(ARC_FIRST_TEN, 10), 970);
  assert.equal(upgradeCost(ARC_FIRST_TEN, 11), 995);
  assert.equal(upgradeCost(ARC_FIRST_TEN, 80), 5464);
  assert.equal(upgradeCost(ARC_FIRST_TEN, 301), 1_280_610);
});

test("ordinary Great Buildings require one blueprint set after level 10", () => {
  const building = { foundationGoods: { wine: 20 } };
  assert.deepEqual(unlockCostsForLevel(building, 10), {
    blueprintSets: 0,
    goods: {},
    resources: {},
  });
  assert.deepEqual(unlockCostsForLevel(building, 11), {
    blueprintSets: 1,
    goods: {},
    resources: {},
  });
});

test("additional unlock resources scale from target level 11", () => {
  const building = {
    foundationGoods: { good_a: 1, good_b: 1 },
    levelUnlockFormula: {
      startLevel: 11,
      blueprintSets: 1,
      goodsPerTypePerStep: 55,
      resourcesPerStep: { money: 97_200, medals: 97_200 },
    },
  };
  assert.deepEqual(unlockCostsForLevel(building, 12), {
    blueprintSets: 1,
    goods: { good_a: 110, good_b: 110 },
    resources: { money: 194_400, medals: 194_400 },
  });
});

test("P2–P5 use Forge Hammer's recursive nearest-five rounding", () => {
  assert.deepEqual(basePositionRewards(1375), [1375, 690, 230, 60, 10]);
});

test("Arc bonus uses Forge Hammer integer rounding", () => {
  assert.deepEqual(
    applyArcBonus([1375, 690, 230, 60, 10], 90),
    [2613, 1311, 437, 114, 19],
  );
});

test("Arc levels map to the displayed contribution bonus", () => {
  assert.equal(arcBonusForLevel(0), 0);
  assert.equal(arcBonusForLevel(1), 10);
  assert.equal(arcBonusForLevel(10), 31);
  assert.equal(arcBonusForLevel(58), 79);
  assert.equal(arcBonusForLevel(59), 79.5);
  assert.equal(arcBonusForLevel(80), 90);
  assert.equal(arcBonusForLevel(101), 92.1);
  assert.equal(arcBonusForLevel(180), 100);
  assert.equal(arcLevelForBonus(90), 80);
  assert.equal(arcLevelForBonus(100), 180);
  assert.throws(() => arcBonusForLevel(181), /0 to 180\+/);
});

test("medal positions use the live game's P1 fractions and whole-unit rounding", () => {
  assert.deepEqual(baseMedalRewards(89145), [89145, 44573, 22286, 8915, 4457]);
});

test("target level uses the matching zero-based reward-table entry", () => {
  const rewards = rewardsForLevel(
    {
      fpP1ByLevel: [5, 10],
      medalP1ByLevel: [13, 17],
      blueprintsByLevel: [
        [0, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
      ],
    },
    2,
    90,
  );
  assert.deepEqual(rewards.forgePoints?.base, [10, 5, 0, 0, 0]);
  assert.deepEqual(rewards.medals?.base, [17, 9, 4, 2, 1]);
  assert.deepEqual(rewards.blueprints?.adjusted, [2, 0, 0, 0, 0]);
});

test("level rows retain cumulative cost when Forge Hammer FP rewards end", () => {
  const rows = buildLevelRows(
    { firstTenLevelCosts: ARC_FIRST_TEN },
    {
      fpP1ByLevel: [5],
      medalP1ByLevel: [13, 17],
      blueprintsByLevel: [
        [0, 0, 0, 0, 0],
        [1, 0, 0, 0, 0],
      ],
    },
    90,
    2,
  );
  assert.equal(rows[1].cumulativeCost, 180);
  assert.equal(rows[1].unlockCosts.blueprintSets, 0);
  assert.equal(rows[1].rewards.forgePoints, null);
  assert.deepEqual(rows[1].rewards.medals?.adjusted, [32, 17, 8, 4, 2]);
});

test("upgrade curve series include FP and every non-blueprint resource cost", () => {
  const rows = [
    {
      cost: 10,
      unlockCosts: {
        blueprintSets: 1,
        goods: { good_a: 2, good_b: 3 },
        resources: { money: 100, medals: 5 },
      },
    },
    {
      cost: 20,
      unlockCosts: {
        blueprintSets: 1,
        goods: { good_a: 4, good_b: 5 },
        resources: { money: 200, medals: 10 },
      },
    },
  ];
  assert.deepEqual(buildUpgradeCostSeries(rows), [
    { id: "forgePoints", values: [10, 20] },
    { id: "goods", values: [5, 9] },
    { id: "medals", values: [5, 10] },
    { id: "money", values: [100, 200] },
  ]);
});

test("base reward curve series include P1 through P5 for each resource", () => {
  const rows = [
    { rewards: { medals: { base: [100, 50, 25, 10, 5] } } },
    { rewards: { medals: { base: [200, 100, 50, 20, 10] } } },
  ];
  assert.deepEqual(buildBaseRewardSeries(rows, "medals"), [
    { position: 1, values: [100, 200] },
    { position: 2, values: [50, 100] },
    { position: 3, values: [25, 50] },
    { position: 4, values: [10, 20] },
    { position: 5, values: [5, 10] },
  ]);
  assert.throws(() => buildBaseRewardSeries(rows, "diamonds"), RangeError);
});

test("Pre-rage analysis applies position Arc bonuses and totals owner requirements", () => {
  const rows = [
    {
      targetLevel: 10,
      cost: 1000,
      unlockCosts: {
        goods: { good_a: 10, good_b: 10 },
        resources: { money: 100, supplies: 50, medals: 5, dark_matter: 7 },
      },
      rewards: { forgePoints: { base: [100, 50, 25, 10, 5] } },
    },
    {
      targetLevel: 11,
      cost: 1200,
      unlockCosts: {
        goods: { good_a: 20, good_b: 20 },
        resources: { money: 200, medals: 15 },
      },
      rewards: { forgePoints: { base: [200, 100, 50, 20, 10] } },
    },
  ];

  const analysis = buildRageAnalysis(rows, 10, 11, [90, 80, 70, 60, 50]);
  assert.deepEqual(analysis.rows[0], {
    targetLevel: 10,
    upgradeForgePoints: 1000,
    contributions: [190, 90, 43, 16, 8],
    ownerForgePoints: 653,
    goodsPerType: 10,
    goods: 20,
    money: 100,
    supplies: 50,
    medals: 5,
    specialResources: { dark_matter: 7 },
  });
  assert.deepEqual(analysis.totals, {
    upgradeForgePoints: 2200,
    contributions: [570, 270, 128, 48, 23],
    ownerForgePoints: 1161,
    goodsPerType: 30,
    goods: 60,
    money: 300,
    supplies: 50,
    medals: 20,
    specialResources: { dark_matter: 7 },
  });
  assert.throws(
    () => buildRageAnalysis(rows, 11, 10, [90, 90, 90, 90, 90]),
    /Beginning level/,
  );
  assert.throws(
    () => buildRageAnalysis(rows, 10, 11, [101, 100, 100, 90, 90]),
    /between 0% and 100%/,
  );
});

test("Shattered Horizon Siphon extends calculated costs and modeled rewards to 301", () => {
  const dataset = JSON.parse(
    readFileSync(new URL("../data/gb-analysis.json", import.meta.url), "utf8"),
  );
  const siphon = dataset.buildings.find(
    (building) => building.id === "X_StellarAgeDiscovery_Landmark1",
  );
  const rows = buildLevelRows(
    siphon,
    {
      fpP1ByLevel: dataset.rewardP1ByEra["24"],
      medalP1ByLevel: dataset.medalP1ByEra["24"],
      blueprintsByLevel: dataset.blueprintsByLevel,
    },
    0,
    301,
  );
  assert.equal(rows[200].cost, 1_623_768);
  assert.equal(rows[200].cumulativeCost, 66_051_010);
  assert.deepEqual(rows[10].unlockCosts, {
    blueprintSets: 1,
    goods: {
      stel_xenocrystals: 275,
      stel_glyph_circuits: 275,
      stel_metamorphic_alloys: 275,
      stel_resonance_cores: 275,
      stel_psionic_conduits: 275,
    },
    resources: { money: 97_200, supplies: 97_200, medals: 97_200 },
  });
  const goodsSeries = buildUpgradeCostSeries(rows).find(({ id }) => id === "goods");
  assert.equal(goodsSeries.values[10], 1_375);
  const rage = buildRageAnalysis(rows, 1, 11, [100, 100, 100, 90, 90]);
  assert.equal(rage.rows[10].goods, 1_375);
  assert.equal(rage.rows[10].goodsPerType, 275);
  assert.equal(rage.totals.goods, 1_375);
  assert.equal(rage.totals.goodsPerType, 275);
  assert.deepEqual(rows[200].rewards.forgePoints?.base, [5975, 2990, 995, 250, 50]);
  assert.deepEqual(rows[200].rewards.medals?.base, [578833, 289417, 144708, 57883, 28942]);
  assert.deepEqual(rows[200].rewards.blueprints?.base, [32, 23, 18, 15, 12]);
  assert.equal(rows[300].cost, 19_182_732);
  assert.equal(rows[300].cumulativeCost, 785_968_562);
  assert.equal(rows[300].unlockCosts.goods.stel_xenocrystals, 80_025);
  assert.equal(goodsSeries.values[300], 400_125);
  assert.equal(rows[300].unlockCosts.resources.money, 28_285_200);
  assert.deepEqual(rows[201].rewards.forgePoints?.base, [6010, 3005, 1000, 250, 50]);
  assert.ok(rows[201].rewards.medals?.base[0] > rows[200].rewards.medals?.base[0]);
  assert.deepEqual(rows[201].rewards.blueprints?.base, [32, 23, 18, 15, 12]);
  assert.deepEqual(rows[300].rewards.forgePoints?.base, [9710, 4855, 1620, 405, 80]);
  assert.deepEqual(rows[300].rewards.medals?.base, [940762, 470381, 235191, 94076, 47038]);
  assert.deepEqual(rows[300].rewards.blueprints?.base, [44, 32, 25, 20, 17]);
});

test("Cosmic Catalyst includes Dark Matter in every pre-rage unlock total", () => {
  const dataset = JSON.parse(
    readFileSync(new URL("../data/gb-analysis.json", import.meta.url), "utf8"),
  );
  const catalyst = dataset.buildings.find(
    (building) => building.name === "Cosmic Catalyst",
  );
  const rows = buildLevelRows(
    catalyst,
    {
      fpP1ByLevel: dataset.rewardP1ByEra[String(catalyst.eraId)],
      medalP1ByLevel: dataset.medalP1ByEra[String(catalyst.eraId)],
      blueprintsByLevel: dataset.blueprintsByLevel,
    },
    0,
    12,
  );
  const rage = buildRageAnalysis(rows, 11, 12, [100, 100, 100, 90, 90]);
  assert.deepEqual(rage.rows[0].specialResources, { dark_matter: 100 });
  assert.deepEqual(rage.rows[1].specialResources, { dark_matter: 200 });
  assert.deepEqual(rage.totals.specialResources, { dark_matter: 300 });
  assert.equal(rage.rows[0].goodsPerType, 150);
  assert.equal(rage.rows[0].goods, 750);
});

test("every Great Building can be analyzed through target level 301", () => {
  const dataset = JSON.parse(
    readFileSync(new URL("../data/gb-analysis.json", import.meta.url), "utf8"),
  );
  for (const building of dataset.buildings) {
    const rows = buildLevelRows(
      building,
      {
        fpP1ByLevel: dataset.rewardP1ByEra[String(building.eraId)],
        medalP1ByLevel: dataset.medalP1ByEra[String(building.eraId)],
        blueprintsByLevel: dataset.blueprintsByLevel,
      },
      90,
      dataset.maxLevel,
    );
    assert.equal(rows.length, 301, building.name);
    assert.equal(rows[300].targetLevel, 301, building.name);
    assert.ok(Number.isFinite(rows[300].cost) && rows[300].cost > 0, building.name);
    assert.ok(rows[300].rewards.forgePoints, `${building.name} FP rewards`);
    assert.ok(rows[300].rewards.medals, `${building.name} medal rewards`);
    assert.ok(rows[300].rewards.blueprints, `${building.name} blueprint rewards`);
  }
});
