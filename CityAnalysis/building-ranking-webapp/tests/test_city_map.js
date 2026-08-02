const test = require("node:test");
const assert = require("node:assert/strict");

const {
  MAX_FILE_BYTES,
  summarizeCityMap,
} = require("../src/city-map.js");

test("reads a zpwd-ref style CityMapData object and infers age", () => {
  const result = summarizeCityMap({
    CityMapData: {
      1: { cityentity_id: "H_VirtualFuture_Townhall", type: "main_building" },
      2: { cityentity_id: "W_AllAge_Camelot", type: "residential" },
      3: { cityentity_id: "W_AllAge_Camelot", type: "residential" },
    },
    CityEntities: { ignored: { name: "Definitions are not map placements" } },
  });

  assert.equal(result.format, "city-map-data");
  assert.equal(result.detectedAge, "VirtualFuture");
  assert.equal(result.totalEntries, 3);
  assert.equal(result.identifiedEntries, 3);
  assert.equal(result.uniqueEntityIds, 2);
  assert.equal(result.counts.get("W_AllAge_Camelot"), 2);
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
            { cityentity_id: "W_AllAge_LoafHouse" },
            { cityentity_id: "W_AllAge_LoafHouse" },
          ],
        },
      },
    },
  ]);

  assert.equal(result.format, "visit-player");
  assert.equal(result.detectedAge, "SpaceAgeSpaceHub");
  assert.equal(result.counts.get("W_AllAge_LoafHouse"), 2);
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

test("file-size limit accommodates full reference exports", () => {
  assert.equal(MAX_FILE_BYTES, 100 * 1024 * 1024);
});
