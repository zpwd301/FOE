(function initializeBuildingRankingPreferences(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_PREFERENCES = api;
})(typeof window !== "undefined" ? window : globalThis, function preferenceFactory() {
  "use strict";

  const STORAGE_KEY = "foe-building-rankings.preferences.v1";
  const SCHEMA_VERSION = 1;

  function isObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function allowedValue(value, allowed) {
    return typeof value === "string" && allowed?.includes(value);
  }

  function boundedNumber(value, minimum, maximum, integer = false) {
    if (typeof value !== "number" || !Number.isFinite(value)) return null;
    if (value < minimum || value > maximum) return null;
    if (integer && !Number.isInteger(value)) return null;
    return value;
  }

  function sanitizePreferences(value, allowed = {}) {
    if (!isObject(value)) return {};
    const sanitized = {};

    if (allowedValue(value.profile, allowed.profiles)) sanitized.profile = value.profile;
    if (allowedValue(value.age, allowed.ages)) sanitized.age = value.age;
    if (allowedValue(value.category, allowed.categories)) sanitized.category = value.category;
    if (allowedValue(value.searchMode, allowed.searchModes)) sanitized.searchMode = value.searchMode;
    if (allowedValue(value.qiRole, allowed.qiRoles)) sanitized.qiRole = value.qiRole;

    if (isObject(value.focus)) {
      const focus = {};
      ["gbgGe", "redBlue", "attackDefense", "unitAge", "fpGoods"].forEach((key) => {
        const number = boundedNumber(value.focus[key], 1, 5, true);
        if (number !== null) focus[key] = number;
      });
      if (Object.keys(focus).length) sanitized.focus = focus;
    }

    if (isObject(value.production)) {
      const production = {};
      ["fp", "goods", "guildGoods", "medals", "specialGoods"].forEach((key) => {
        const number = boundedNumber(value.production[key], 0, 1_000_000_000_000);
        if (number !== null) production[key] = number;
      });
      if (Object.keys(production).length) sanitized.production = production;
    }

    if (isObject(value.filters)) {
      const filters = {};
      if (Array.isArray(value.filters.strengths)) {
        const strengths = [...new Set(value.filters.strengths.filter((item) => allowedValue(item, allowed.strengths)))];
        filters.strengths = strengths;
      }
      const minimumArea = value.filters.minArea === null
        ? null
        : boundedNumber(value.filters.minArea, 0, 1_000_000, true);
      const maximumArea = value.filters.maxArea === null
        ? null
        : boundedNumber(value.filters.maxArea, 0, 1_000_000, true);
      const areaRangeIsValid = minimumArea === null || maximumArea === null || minimumArea <= maximumArea;
      if (areaRangeIsValid && (minimumArea !== null || value.filters.minArea === null)) filters.minArea = minimumArea;
      if (areaRangeIsValid && (maximumArea !== null || value.filters.maxArea === null)) filters.maxArea = maximumArea;
      if (typeof value.filters.noRoadOnly === "boolean") filters.noRoadOnly = value.filters.noRoadOnly;
      if (allowedValue(value.filters.topN, allowed.topNs)) filters.topN = value.filters.topN;
      if (Object.keys(filters).length) sanitized.filters = filters;
    }

    if (allowedValue(value.weightMode, allowed.weightModes)) sanitized.weightMode = value.weightMode;

    if (isObject(value.customWeights)) {
      const attributeKeys = new Set(allowed.attributeKeys || []);
      const customWeights = {};
      (allowed.weightProfiles || []).forEach((profile) => {
        const source = value.customWeights[profile];
        if (!isObject(source)) return;
        const weights = {};
        Object.entries(source).forEach(([key, weight]) => {
          if (!attributeKeys.has(key)) return;
          const maximum = profile === "kits" ? 10 : 1000;
          const number = boundedNumber(weight, 0, maximum, profile === "kits");
          if (number !== null) weights[key] = number;
        });
        customWeights[profile] = weights;
      });
      if (Object.keys(customWeights).length) sanitized.customWeights = customWeights;
    }

    if (isObject(value.sort)
      && allowedValue(value.sort.key, allowed.sortKeys)
      && allowedValue(value.sort.dir, ["asc", "desc"])) {
      sanitized.sort = { key: value.sort.key, dir: value.sort.dir };
    }

    return sanitized;
  }

  function createPreferenceStore(storage, options = {}) {
    const key = options.key || STORAGE_KEY;
    const version = options.version || SCHEMA_VERSION;
    let lastSnapshot = null;

    function snapshot(values) {
      return JSON.stringify(values);
    }

    return {
      get available() {
        return Boolean(storage);
      },

      read() {
        if (!storage) return null;
        try {
          const raw = storage.getItem(key);
          if (!raw) return null;
          const envelope = JSON.parse(raw);
          if (!isObject(envelope) || envelope.schemaVersion !== version || !isObject(envelope.values)) return null;
          lastSnapshot = snapshot(envelope.values);
          return envelope.values;
        } catch (_error) {
          return null;
        }
      },

      remember(values) {
        lastSnapshot = snapshot(values);
      },

      save(values) {
        if (!storage) return "unavailable";
        try {
          const nextSnapshot = snapshot(values);
          if (nextSnapshot === lastSnapshot) return "unchanged";
          storage.setItem(key, JSON.stringify({
            schemaVersion: version,
            savedAt: new Date().toISOString(),
            values,
          }));
          lastSnapshot = nextSnapshot;
          return "saved";
        } catch (_error) {
          return "error";
        }
      },

      clear() {
        lastSnapshot = null;
        if (!storage) return "unavailable";
        try {
          storage.removeItem(key);
          return "cleared";
        } catch (_error) {
          return "error";
        }
      },
    };
  }

  return {
    STORAGE_KEY,
    SCHEMA_VERSION,
    sanitizePreferences,
    createPreferenceStore,
  };
});
