(function initializeCityMapReader(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_CITY_MAP = api;
})(typeof window !== "undefined" ? window : globalThis, function cityMapReaderFactory() {
  "use strict";

  const MAX_FILE_BYTES = 100 * 1024 * 1024;
  const PRODUCTION_KEYS = ["fp", "goods", "guildGoods", "medals", "specialGoods"];
  const GREAT_BUILDING_PERCENTAGE_BOOSTS = {
    algorithmic_core: { category: "specialGoods", label: "A.I. Core" },
  };

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

  function isGreatBuilding(entry) {
    return isObject(entry) && String(entry.type || "").toLowerCase() === "greatbuilding";
  }

  function greatBuildingBonus(entry) {
    if (!isGreatBuilding(entry) || !isObject(entry.bonus)) return null;
    const type = String(entry.bonus.type || "").trim().toLowerCase();
    const value = Number(entry.bonus.value);
    if (!type || !Number.isFinite(value)) return null;
    const amount = Number(entry.bonus.amount);
    return {
      entityId: entityId(entry),
      level: entityLevel(entry),
      type,
      value,
      amount: Number.isFinite(amount) ? amount : null,
    };
  }

  function sumGoods(goods) {
    if (!Array.isArray(goods)) return 0;
    return goods.reduce((sum, item) => {
      const value = Number(item?.value);
      return sum + (Number.isFinite(value) && value > 0 ? value : 0);
    }, 0);
  }

  function sumResources(resources) {
    if (!isObject(resources)) return 0;
    return Object.values(resources).reduce((sum, rawValue) => {
      const value = Number(rawValue);
      return sum + (Number.isFinite(value) && value > 0 ? value : 0);
    }, 0);
  }

  function greatBuildingProduction(entry) {
    if (!isGreatBuilding(entry)) return null;
    const product = entry.state?.current_product;
    if (!isObject(product)) return null;
    const productionTime = Number(product.production_time);
    const dailyFactor = Number.isFinite(productionTime) && productionTime > 0
      ? 86400 / productionTime
      : 1;
    const name = String(product.name || product.asset_name || "").trim().toLowerCase();
    const resources = product.product?.resources;
    const resourceTotal = sumResources(resources);
    const goodsTotal = sumGoods(product.goods);
    const production = Object.fromEntries(PRODUCTION_KEYS.map((key) => [key, 0]));

    if (name === "strategy_points") {
      production.fp = Math.max(0, Number(resources?.strategy_points) || resourceTotal) * dailyFactor;
    } else if (name === "medals") {
      production.medals = Math.max(0, Number(resources?.medals) || resourceTotal) * dailyFactor;
    } else if (name === "clan_goods" || name === "guild_goods") {
      production.guildGoods = Math.max(goodsTotal, resourceTotal) * dailyFactor;
    } else if (name === "special_goods") {
      production.specialGoods = Math.max(goodsTotal, resourceTotal) * dailyFactor;
    } else if (name === "goods") {
      production.goods = Math.max(goodsTotal, resourceTotal) * dailyFactor;
    }

    if (!PRODUCTION_KEYS.some((key) => production[key] > 0)) return null;
    return {
      entityId: entityId(entry),
      level: entityLevel(entry),
      productionTime,
      production,
    };
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
    const greatBuildingEntityIds = new Set();
    const greatBuildingBonuses = [];
    const greatBuildingProductions = [];
    for (const entry of extracted.entries) {
      const id = entityId(entry);
      if (!id) continue;
      counts.set(id, (counts.get(id) || 0) + 1);
      if (isGreatBuilding(entry)) {
        greatBuildingEntityIds.add(id);
        const bonus = greatBuildingBonus(entry);
        if (bonus) greatBuildingBonuses.push(bonus);
        const production = greatBuildingProduction(entry);
        if (production) greatBuildingProductions.push(production);
      }
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
      greatBuildingBonuses,
      greatBuildingEntityIds,
      greatBuildingProductions,
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
      if (summary?.greatBuildingEntityIds instanceof Set
          && summary.greatBuildingEntityIds.has(group.entityId)) return null;
      const cityRecord = group.age
        ? recordsForAge(group.age, cityRecordsByAge, cityAgeRecordMaps).get(group.entityId)
        : null;
      const placedBenchmarkRecord = group.age
        ? recordsForAge(group.age, recordsByAge, ageRecordMaps).get(group.entityId)
        : null;
      const record = cityRecord || placedBenchmarkRecord;
      return record ? {
        ...group,
        record,
        usedBenchmarkFallback: false,
      } : null;
    }).filter(Boolean);
  }

  function finiteAttribute(record, key) {
    if (!key) return 0;
    const value = Number(record?.attrs?.[key]);
    return Number.isFinite(value) ? value : 0;
  }

  function calculateProductionComponents(groups, attributeKeys) {
    const base = Object.fromEntries(PRODUCTION_KEYS.map((key) => [key, 0]));
    const placedBoostPercentages = Object.fromEntries(PRODUCTION_KEYS.map((key) => [key, 0]));
    const specialGoodsCollections = [];
    let matchedCopies = 0;

    for (const group of groups) {
      const count = Number(group.count);
      if (!Number.isFinite(count) || count <= 0) continue;
      const specialGoods = Math.max(0, finiteAttribute(group.record, attributeKeys.specialGoods));
      const totalGoods = Math.max(0, finiteAttribute(group.record, attributeKeys.goods));
      base.fp += Math.max(0, finiteAttribute(group.record, attributeKeys.fp)) * count;
      base.goods += Math.max(0, totalGoods - specialGoods) * count;
      base.guildGoods += Math.max(0, finiteAttribute(group.record, attributeKeys.guildGoods)) * count;
      base.medals += Math.max(0, finiteAttribute(group.record, attributeKeys.medals)) * count;
      base.specialGoods += specialGoods * count;
      placedBoostPercentages.fp += Math.max(0, finiteAttribute(group.record, attributeKeys.boostFp)) * count;
      placedBoostPercentages.goods += Math.max(0, finiteAttribute(group.record, attributeKeys.boostGoods)) * count;
      placedBoostPercentages.guildGoods += Math.max(0, finiteAttribute(group.record, attributeKeys.boostGuildGoods)) * count;
      placedBoostPercentages.medals += Math.max(0, finiteAttribute(group.record, attributeKeys.boostMedals)) * count;
      placedBoostPercentages.specialGoods += Math.max(0, finiteAttribute(group.record, attributeKeys.boostSpecialGoods)) * count;
      for (let copy = 0; copy < count && specialGoods > 0; copy += 1) {
        specialGoodsCollections.push(specialGoods);
      }
      matchedCopies += count;
    }

    specialGoodsCollections.sort((left, right) => right - left);
    return { base, placedBoostPercentages, specialGoodsCollections, matchedCopies };
  }

  function calculateBaseProduction(
    summary,
    ages,
    benchmarkRecords,
    recordsByAge = {},
    cityRecordsByAge = recordsByAge,
    attributeKeys = {}
  ) {
    const groups = resolvePlacementRecords(
      summary,
      ages,
      benchmarkRecords,
      recordsByAge,
      cityRecordsByAge
    );
    const components = calculateProductionComponents(groups, attributeKeys);
    return {
      ...components.base,
      matchedCopies: components.matchedCopies,
      matchedAgeGroups: groups.length,
    };
  }

  function productionBaseWithOverrides(calculatedBase, baseOverrides) {
    return Object.fromEntries(PRODUCTION_KEYS.map((key) => {
      const override = Number(baseOverrides?.[key]);
      return [key, Number.isFinite(override) && override >= 0 ? override : calculatedBase[key]];
    }));
  }

  function calculateBoostedProduction(
    summary,
    ages,
    benchmarkRecords,
    recordsByAge = {},
    cityRecordsByAge = recordsByAge,
    attributeKeys = {},
    baseOverrides = null
  ) {
    const groups = resolvePlacementRecords(
      summary,
      ages,
      benchmarkRecords,
      recordsByAge,
      cityRecordsByAge
    );
    const components = calculateProductionComponents(groups, attributeKeys);
    const base = productionBaseWithOverrides(components.base, baseOverrides);
    const boosted = Object.fromEntries(PRODUCTION_KEYS.map((key) => [
      key,
      base[key] * (1 + components.placedBoostPercentages[key] / 100),
    ]));
    const greatBuildingBoosts = [];

    for (const bonus of summary?.greatBuildingBonuses || []) {
      const config = GREAT_BUILDING_PERCENTAGE_BOOSTS[bonus.type];
      if (!config || bonus.value <= 0) continue;
      const eligibleCollections = components.specialGoodsCollections.length;
      const charges = Number.isFinite(bonus.amount) && bonus.amount >= 0
        ? Math.floor(bonus.amount)
        : eligibleCollections;
      const appliedCollections = Math.min(charges, eligibleCollections);
      const coveredCalculatedBase = components.specialGoodsCollections
        .slice(0, appliedCollections)
        .reduce((sum, value) => sum + value, 0);
      const coverage = components.base[config.category] > 0
        ? Math.min(1, coveredCalculatedBase / components.base[config.category])
        : 0;
      const productionAfterPlacedBoosts = base[config.category]
        * (1 + components.placedBoostPercentages[config.category] / 100);
      const added = productionAfterPlacedBoosts * coverage * bonus.value / 100;
      boosted[config.category] += added;
      greatBuildingBoosts.push({
        ...bonus,
        label: config.label,
        category: config.category,
        charges,
        eligibleCollections,
        appliedCollections,
        coverage,
        added,
      });
    }

    const effectiveBoostPercentages = Object.fromEntries(PRODUCTION_KEYS.map((key) => [
      key,
      base[key] > 0 ? (boosted[key] - base[key]) * 100 / base[key] : 0,
    ]));
    const nonBoostableProduction = Object.fromEntries(PRODUCTION_KEYS.map((key) => [
      key,
      (summary?.greatBuildingProductions || []).reduce(
        (sum, production) => sum + Math.max(0, Number(production?.production?.[key]) || 0),
        0
      ),
    ]));
    const total = Object.fromEntries(PRODUCTION_KEYS.map((key) => [
      key,
      boosted[key] + nonBoostableProduction[key],
    ]));

    return {
      base,
      boosted,
      total,
      calculatedBase: components.base,
      placedBoostPercentages: components.placedBoostPercentages,
      effectiveBoostPercentages,
      greatBuildingBoosts,
      greatBuildingProductions: summary?.greatBuildingProductions || [],
      nonBoostableProduction,
      excludedDoubleCollectionCount: (summary?.greatBuildingBonuses || [])
        .filter((bonus) => bonus.type === "double_collection")
        .length,
      matchedCopies: components.matchedCopies,
      matchedAgeGroups: groups.length,
    };
  }

  return {
    MAX_FILE_BYTES,
    calculateBaseProduction,
    calculateBoostedProduction,
    entityId,
    entityLevel,
    extractCityMap,
    placementAgeGroups,
    resolvePlacementRecords,
    summarizeCityMap,
  };
});
