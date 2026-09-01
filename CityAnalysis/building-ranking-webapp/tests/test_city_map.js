const test = require("node:test");
const assert = require("node:assert/strict");

const {
  MAX_FILE_BYTES,
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
    },
    CityEntities: { ignored: { name: "Definitions are not map placements" } },
  });

  assert.equal(result.format, "city-map-data");
  assert.equal(result.detectedAge, "VirtualFuture");
  assert.equal(result.totalEntries, 3);
  assert.equal(result.identifiedEntries, 3);
  assert.equal(result.ageIdentifiedEntries, 2);
  assert.equal(result.uniqueEntityIds, 2);
  assert.equal(result.uniqueEntityAgeGroups, 2);
  assert.deepEqual(result.placementLevels, [16]);
  assert.equal(result.counts.get("W_AllAge_Camelot"), 2);
  assert.equal(result.countsByEntityLevel.get("W_AllAge_Camelot").get(16), 2);
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

test("uses each placement age's record and falls back only when necessary", () => {
  const summary = summarizeCityMap({
    CityMapData: [
      { cityentity_id: "A", level: 2 },
      { cityentity_id: "A", level: 3 },
      { cityentity_id: "B", level: 2 },
      { cityentity_id: "C", level: 2 },
      { cityentity_id: "D", level: 2 },
    ],
  });
  const ages = ["Age0", "Age1", "Age2", "Age3"].map((key) => ({ key }));
  const benchmarkRecords = [
    { entityId: "A", attrs: { goods: 40 } },
    { entityId: "B", attrs: { goods: 50 } },
    { entityId: "C", attrs: { goods: 60 } },
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
      { entityId: "C", age: "Age2", goods: 60, fallback: true },
      { entityId: "D", age: "Age2", goods: 15, fallback: false },
    ]
  );
});

test("file-size limit accommodates full reference exports", () => {
  assert.equal(MAX_FILE_BYTES, 100 * 1024 * 1024);
});
