(function initializeCityMapReader(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_CITY_MAP = api;
})(typeof window !== "undefined" ? window : globalThis, function cityMapReaderFactory() {
  "use strict";

  const MAX_FILE_BYTES = 100 * 1024 * 1024;

  function isObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function mapEntries(cityMap) {
    if (Array.isArray(cityMap)) return cityMap;
    if (!isObject(cityMap)) return [];
    if (Array.isArray(cityMap.entities)) return cityMap.entities;
    return Object.values(cityMap).filter(isObject);
  }

  function entityId(entry) {
    if (!isObject(entry)) return "";
    const value = entry.cityentity_id ?? entry.cityEntityId ?? entry.city_entity_id;
    return typeof value === "string" ? value.trim() : "";
  }

  function entityLevel(entry) {
    if (!isObject(entry)) return null;
    const numeric = Number(entry.level);
    return Number.isInteger(numeric) && numeric >= 0 ? numeric : null;
  }

  function townHallAge(entries) {
    for (const entry of entries) {
      const match = /^H_([^_]+)_Townhall$/i.exec(entityId(entry));
      if (match) return match[1];
    }
    return "";
  }

  function extractCityMap(payload) {
    if (isObject(payload) && payload.CityMapData !== undefined) {
      const entries = mapEntries(payload.CityMapData);
      return {
        entries,
        detectedAge: String(payload.CurrentEra || payload.currentEra || townHallAge(entries) || ""),
        format: "city-map-data",
      };
    }

    const candidates = Array.isArray(payload) ? payload : [payload];
    for (const candidate of candidates) {
      if (!isObject(candidate)) continue;
      const responseData = candidate.responseData;
      const cityMap = responseData?.city_map ?? responseData?.cityMap ?? candidate.city_map ?? candidate.cityMap;
      if (cityMap === undefined) continue;
      const entries = mapEntries(cityMap);
      return {
        entries,
        detectedAge: String(
          responseData?.other_player_era
            || responseData?.otherPlayerEra
            || candidate.other_player_era
            || townHallAge(entries)
            || ""
        ),
        format: responseData?.city_map !== undefined || responseData?.cityMap !== undefined
          ? "visit-player"
          : "city-map",
      };
    }

    throw new Error("No supported city map was found in this file.");
  }

  function summarizeCityMap(payload) {
    const extracted = extractCityMap(payload);
    if (!extracted.entries.length) throw new Error("The city map does not contain any entries.");

    const counts = new Map();
    const countsByEntityLevel = new Map();
    for (const entry of extracted.entries) {
      const id = entityId(entry);
      if (!id) continue;
      counts.set(id, (counts.get(id) || 0) + 1);
      const level = entityLevel(entry);
      if (!countsByEntityLevel.has(id)) countsByEntityLevel.set(id, new Map());
      const levelCounts = countsByEntityLevel.get(id);
      levelCounts.set(level, (levelCounts.get(level) || 0) + 1);
    }
    if (!counts.size) throw new Error("The city map does not contain recognizable building IDs.");

    const placementLevels = new Set();
    let ageIdentifiedEntries = 0;
    let uniqueEntityAgeGroups = 0;
    for (const levelCounts of countsByEntityLevel.values()) {
      uniqueEntityAgeGroups += levelCounts.size;
      for (const [level, count] of levelCounts) {
        if (level === null) continue;
        placementLevels.add(level);
        ageIdentifiedEntries += count;
      }
    }

    return {
      counts,
      countsByEntityLevel,
      detectedAge: extracted.detectedAge,
      format: extracted.format,
      totalEntries: extracted.entries.length,
      identifiedEntries: Array.from(counts.values()).reduce((sum, count) => sum + count, 0),
      ageIdentifiedEntries,
      placementLevels: [...placementLevels].sort((left, right) => left - right),
      uniqueEntityIds: counts.size,
      uniqueEntityAgeGroups,
    };
  }

  function placementAgeGroups(summary, ages, rankableEntityIds = null) {
    if (!(summary?.countsByEntityLevel instanceof Map) || !Array.isArray(ages)) return [];
    const groups = [];
    for (const [id, levelCounts] of summary.countsByEntityLevel) {
      if (rankableEntityIds instanceof Set && !rankableEntityIds.has(id)) continue;
      for (const [level, count] of levelCounts) {
        const age = Number.isInteger(level) ? String(ages[level]?.key || "") : "";
        groups.push({ entityId: id, level, age, count });
      }
    }
    groups.sort((left, right) => (
      left.entityId.localeCompare(right.entityId)
      || Number(left.level ?? Number.MAX_SAFE_INTEGER) - Number(right.level ?? Number.MAX_SAFE_INTEGER)
    ));
    return groups;
  }

  function resolvePlacementRecords(
    summary,
    ages,
    benchmarkRecords,
    recordsByAge = {},
    cityRecordsByAge = recordsByAge
  ) {
    if (!Array.isArray(benchmarkRecords)) return [];
    const benchmarkById = new Map(benchmarkRecords.map((record) => [record.entityId, record]));
    const ageRecordMaps = new Map();
    const cityAgeRecordMaps = new Map();
    const recordsForAge = (age, source, cache) => {
      if (!cache.has(age)) {
        cache.set(
          age,
          new Map((source[age] || []).map((record) => [record.entityId, record]))
        );
      }
      return cache.get(age);
    };
    return placementAgeGroups(summary, ages).map((group) => {
      const cityRecord = group.age
        ? recordsForAge(group.age, cityRecordsByAge, cityAgeRecordMaps).get(group.entityId)
        : null;
      const placedBenchmarkRecord = group.age
        ? recordsForAge(group.age, recordsByAge, ageRecordMaps).get(group.entityId)
        : null;
      const record = cityRecord || placedBenchmarkRecord || benchmarkById.get(group.entityId);
      return record ? {
        ...group,
        record,
        usedBenchmarkFallback: !cityRecord,
      } : null;
    }).filter(Boolean);
  }

  return {
    MAX_FILE_BYTES,
    entityId,
    entityLevel,
    extractCityMap,
    placementAgeGroups,
    resolvePlacementRecords,
    summarizeCityMap,
  };
});
