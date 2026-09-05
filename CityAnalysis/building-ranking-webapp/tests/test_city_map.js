const test = require("node:test");
const assert = require("node:assert/strict");

const {
  MAX_FILE_BYTES,
  calculateBaseProduction,
  calculateBoostedProduction,
  entityLevel,
  placementAgeGroups,
  resolvePlacementRecords,
  summarizeCityMap,
} = require("../src/city-map.js");

test("reads a zpwd-ref style CityMapData object and infers age", () => {
  const result = summarizeCityMap({
    CityMapData: {
      1: { cityentity_id: "H_VirtualFuture_Townhall", type: "main_building" },
      2: { cityentity_id: "W_AllAge_Camelot", type: "residential", level: 16 },
      3: { cityentity_id: "W_AllAge_Camelot", type: "residential", level: 16 },
      4: {
        cityentity_id: "X_SpaceAgeJupiterMoon_Landmark1",
        type: "greatbuilding",
        level: 70,
        bonus: { type: "algorithmic_core", value: 42.91, amount: 9 },
        state: {
          current_product: {
            name: "clan_goods",
            production_time: 86400,
            goods: [{ value: 100 }, { value: 120 }],
          },
        },
      },
    },
    CityEntities: { ignored: { name: "Definitions are not map placements" } },
  });

  assert.equal(result.format, "city-map-data");
  assert.equal(result.detectedAge, "VirtualFuture");
  assert.equal(result.totalEntries, 4);
  assert.equal(result.identifiedEntries, 4);
  assert.equal(result.ageIdentifiedEntries, 3);
  assert.equal(result.uniqueEntityIds, 3);
  assert.equal(result.uniqueEntityAgeGroups, 3);
  assert.deepEqual(result.placementLevels, [16, 70]);
  assert.equal(result.counts.get("W_AllAge_Camelot"), 2);
  assert.equal(result.countsByEntityLevel.get("W_AllAge_Camelot").get(16), 2);
  assert.deepEqual(result.greatBuildingBonuses, [{
    entityId: "X_SpaceAgeJupiterMoon_Landmark1",
    level: 70,
    type: "algorithmic_core",
    value: 42.91,
    amount: 9,
  }]);
  assert.deepEqual(result.greatBuildingProductions, [{
    entityId: "X_SpaceAgeJupiterMoon_Landmark1",
    level: 70,
    productionTime: 86400,
    production: {
      fp: 0,
      goods: 0,
      guildGoods: 220,
      medals: 0,
      specialGoods: 0,
    },
  }]);
});

test("reads a Raist-style visitPlayer capture and uses its explicit era", () => {
  const result = summarizeCityMap([
    { requestClass: "StartupService", responseData: { city: "ignored" } },
    {
      requestClass: "OtherPlayerService",
      requestMethod: "visitPlayer",
      responseData: {
        other_player_era: "SpaceAgeSpaceHub",
        city_map: {
          entities: [
            { cityentity_id: "H_SpaceAgeSpaceHub_Townhall" },
            { cityentity_id: "W_AllAge_LoafHouse", level: 12 },
            { cityentity_id: "W_AllAge_LoafHouse", level: 11 },
          ],
        },
      },
    },
  ]);

  assert.equal(result.format, "visit-player");
  assert.equal(result.detectedAge, "SpaceAgeSpaceHub");
  assert.equal(result.counts.get("W_AllAge_LoafHouse"), 2);
  assert.equal(result.countsByEntityLevel.get("W_AllAge_LoafHouse").get(11), 1);
  assert.equal(result.countsByEntityLevel.get("W_AllAge_LoafHouse").get(12), 1);
  assert.deepEqual(result.placementLevels, [11, 12]);
});

test("accepts alternate entity ID casing and counts only recognizable entries", () => {
  const result = summarizeCityMap({
    city_map: {
      entities: [
        { cityEntityId: "A" },
        { city_entity_id: "B" },
        { id: 3 },
      ],
    },
  });

  assert.equal(result.totalEntries, 3);
  assert.equal(result.identifiedEntries, 2);
  assert.deepEqual(Array.from(result.counts.entries()), [["A", 1], ["B", 1]]);
});

test("rejects files without a supported city map", () => {
  assert.throws(
    () => summarizeCityMap({ CityEntities: {} }),
    /No supported city map/
  );
  assert.throws(
    () => summarizeCityMap({ CityMapData: {} }),
    /does not contain any entries/
  );
});

test("normalizes valid placement levels and rejects non-age values", () => {
  assert.equal(entityLevel({ level: 18 }), 18);
  assert.equal(entityLevel({ level: "12" }), 12);
  assert.equal(entityLevel({ level: -1 }), null);
  assert.equal(entityLevel({ level: 2.5 }), null);
  assert.equal(entityLevel({ level: "unknown" }), null);
  assert.equal(entityLevel({}), null);
});

test("converts mixed placement levels into rankable age groups", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 3 },
      { cityentity_id: "B", level: 12 },
      { cityentity_id: "C" },
    ],
  });
  const ages = Array.from({ length: 13 }, (_value, level) => ({ key: `Age${level}` }));

  assert.deepEqual(
    placementAgeGroups(summary, ages, new Set(["A", "C"])),
    [
      { entityId: "A", level: 2, age: "Age2", count: 2 },
      { entityId: "A", level: 3, age: "Age3", count: 1 },
      { entityId: "C", level: null, age: "", count: 1 },
    ]
  );
});

test("uses only matching placement-age records without cross-age fallbacks", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 3 },
      { cityentity_id: "B", level: 2 },
      { cityentity_id: "C", level: 2 },
      { cityentity_id: "D", level: 2 },
      { cityentity_id: "E" },
    ],
  });
  const ages = ["Age0", "Age1", "Age2", "Age3"].map((key) => ({ key }));
  const benchmarkRecords = [
    { entityId: "A", attrs: { goods: 40 } },
    { entityId: "B", attrs: { goods: 50 } },
    { entityId: "C", attrs: { goods: 60 } },
    { entityId: "E", attrs: { goods: 70 } },
  ];
  const recordsByAge = {
    Age2: [
      { entityId: "A", attrs: { goods: 20 } },
      { entityId: "B", attrs: { goods: 25 } },
    ],
    Age3: [{ entityId: "A", attrs: { goods: 30 } }],
  };
  const cityRecordsByAge = {
    Age2: [
      ...recordsByAge.Age2,
      { entityId: "D", attrs: { goods: 15 } },
    ],
    Age3: recordsByAge.Age3,
  };
  const resolved = resolvePlacementRecords(
    summary,
    ages,
    benchmarkRecords,
    recordsByAge,
    cityRecordsByAge
  );

  assert.deepEqual(
    resolved.map((group) => ({
      entityId: group.entityId,
      age: group.age,
      goods: group.record.attrs.goods,
      fallback: group.usedBenchmarkFallback,
    })),
    [
      { entityId: "A", age: "Age2", goods: 20, fallback: false },
      { entityId: "A", age: "Age3", goods: 30, fallback: false },
      { entityId: "B", age: "Age2", goods: 25, fallback: false },
      { entityId: "D", age: "Age2", goods: 15, fallback: false },
    ]
  );
});

test("calculates base production from matched copies at their placed ages", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 3 },
      { cityentity_id: "B" },
      { cityentity_id: "unmatched", level: 2 },
      { cityentity_id: "wrong-age-only", level: 2 },
      { cityentity_id: "X_GreatBuilding", type: "greatbuilding" },
    ],
  });
  const ages = ["Age0", "Age1", "Age2", "Age3"].map((key) => ({ key }));
  const benchmarkRecords = [
    { entityId: "B", attrs: { fp: 7, goods: 11, guildGoods: 1, medals: 50, specialGoods: 1 } },
    { entityId: "wrong-age-only", attrs: { fp: 1000, goods: 1000 } },
    { entityId: "X_GreatBuilding", attrs: { fp: 1000, goods: 1000, medals: 1000 } },
  ];
  const cityRecordsByAge = {
    Age2: [
      { entityId: "A", attrs: { fp: 10, goods: 30, guildGoods: 4, medals: 100, specialGoods: 5 } },
    ],
    Age3: [
      { entityId: "A", attrs: { fp: 20, goods: 40, guildGoods: 5, medals: 200, specialGoods: 10 } },
    ],
  };
  const result = calculateBaseProduction(
    summary,
    ages,
    benchmarkRecords,
    {},
    cityRecordsByAge,
    { fp: "fp", goods: "goods", guildGoods: "guildGoods", medals: "medals", specialGoods: "specialGoods" }
  );

  assert.deepEqual(result, {
    fp: 40,
    goods: 80,
    guildGoods: 13,
    medals: 400,
    specialGoods: 20,
    matchedCopies: 3,
    matchedAgeGroups: 2,
  });
});

test("calculates boosted production with placed boosts and charge-limited A.I. Core", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 3 },
      {
        cityentity_id: "X_SpaceAgeJupiterMoon_Landmark1",
        type: "greatbuilding",
        level: 70,
        bonus: { type: "algorithmic_core", value: 50, amount: 2 },
        state: {
          current_product: {
            name: "clan_goods",
            production_time: 86400,
            goods: [{ value: 2 }, { value: 3 }],
          },
        },
      },
      {
        cityentity_id: "X_OceanicFuture_Landmark3",
        type: "greatbuilding",
        level: 100,
        bonus: { type: "double_collection", value: 70, amount: 14 },
        state: {
          current_product: {
            name: "medals",
            production_time: 86400,
            product: { resources: { medals: 7 } },
          },
        },
      },
      {
        cityentity_id: "X_Fp_GreatBuilding",
        type: "greatbuilding",
        level: 80,
        state: {
          current_product: {
            name: "strategy_points",
            production_time: 86400,
            product: { resources: { strategy_points: 11 } },
          },
        },
      },
      {
        cityentity_id: "X_Goods_GreatBuilding",
        type: "greatbuilding",
        level: 60,
        state: {
          current_product: {
            name: "goods",
            production_time: 172800,
            goods: [{ value: 8 }, { value: 12 }],
          },
        },
      },
      {
        cityentity_id: "X_Special_GreatBuilding",
        type: "greatbuilding",
        level: 40,
        state: {
          current_product: {
            name: "special_goods",
            production_time: 86400,
            product: { resources: { promethium: 8 } },
          },
        },
      },
    ],
  });
  const ages = ["Age0", "Age1", "Age2", "Age3"].map((key) => ({ key }));
  const cityRecordsByAge = {
    Age2: [{
      entityId: "A",
      attrs: {
        fp: 10,
        goods: 30,
        guildGoods: 4,
        medals: 100,
        specialGoods: 5,
        boostFp: 10,
        boostGoods: 5,
        boostGuildGoods: 3,
        boostSpecialGoods: 2,
      },
    }],
    Age3: [{
      entityId: "A",
      attrs: {
        fp: 20,
        goods: 40,
        guildGoods: 5,
        medals: 200,
        specialGoods: 10,
        boostFp: 5,
        boostGoods: 10,
        boostGuildGoods: 4,
        boostSpecialGoods: 1,
      },
    }],
  };
  const attributeKeys = {
    fp: "fp",
    goods: "goods",
    guildGoods: "guildGoods",
    medals: "medals",
    specialGoods: "specialGoods",
    boostFp: "boostFp",
    boostGoods: "boostGoods",
    boostGuildGoods: "boostGuildGoods",
    boostMedals: "boostMedals",
    boostSpecialGoods: "boostSpecialGoods",
  };
  const result = calculateBoostedProduction(
    summary,
    ages,
    [],
    {},
    cityRecordsByAge,
    attributeKeys,
    { specialGoods: 40 }
  );

  assert.deepEqual(result.base, {
    fp: 40,
    goods: 80,
    guildGoods: 13,
    medals: 400,
    specialGoods: 40,
  });
  assert.deepEqual(result.placedBoostPercentages, {
    fp: 25,
    goods: 20,
    guildGoods: 10,
    medals: 0,
    specialGoods: 5,
  });
  assert.deepEqual(result.boosted, {
    fp: 50,
    goods: 96,
    guildGoods: 14.3,
    medals: 400,
    specialGoods: 57.75,
  });
  assert.deepEqual(result.nonBoostableProduction, {
    fp: 11,
    goods: 10,
    guildGoods: 5,
    medals: 7,
    specialGoods: 8,
  });
  assert.deepEqual(result.total, {
    fp: 61,
    goods: 106,
    guildGoods: 19.3,
    medals: 407,
    specialGoods: 65.75,
  });
  assert.equal(result.greatBuildingBoosts.length, 1);
  assert.deepEqual(
    {
      label: result.greatBuildingBoosts[0].label,
      charges: result.greatBuildingBoosts[0].charges,
      eligibleCollections: result.greatBuildingBoosts[0].eligibleCollections,
      appliedCollections: result.greatBuildingBoosts[0].appliedCollections,
      coverage: result.greatBuildingBoosts[0].coverage,
      added: result.greatBuildingBoosts[0].added,
    },
    {
      label: "A.I. Core",
      charges: 2,
      eligibleCollections: 3,
      appliedCollections: 2,
      coverage: 0.75,
      added: 15.75,
    }
  );
  assert.equal(result.excludedDoubleCollectionCount, 1);
});

test("multiplies placed special-goods boosts by the A.I. Core factor", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "SPECIAL_PRODUCER", level: 1 },
      { cityentity_id: "QUEEN_ANNE", level: 1 },
      {
        cityentity_id: "X_SpaceAgeJupiterMoon_Landmark1",
        type: "greatbuilding",
        level: 70,
        bonus: { type: "algorithmic_core", value: 42.91, amount: 1 },
      },
    ],
  });
  const ages = [{ key: "Age0" }, { key: "Age1" }];
  const cityRecordsByAge = {
    Age1: [
      { entityId: "SPECIAL_PRODUCER", attrs: { specialGoods: 100 } },
      { entityId: "QUEEN_ANNE", attrs: { boostSpecialGoods: 5 } },
    ],
  };

  const result = calculateBoostedProduction(
    summary,
    ages,
    [],
    {},
    cityRecordsByAge,
    { specialGoods: "specialGoods", boostSpecialGoods: "boostSpecialGoods" }
  );

  assert.equal(result.placedBoostPercentages.specialGoods, 5);
  assert.equal(result.greatBuildingBoosts[0].coverage, 1);
  assert.equal(result.boosted.specialGoods, 100 * 1.05 * 1.4291);
});

test("file-size limit accommodates full reference exports", () => {
  assert.equal(MAX_FILE_BYTES, 100 * 1024 * 1024);
});
