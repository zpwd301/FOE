const test = require("node:test");
const assert = require("node:assert/strict");

const {
  STORAGE_KEY,
  SCHEMA_VERSION,
  createPreferenceStore,
  sanitizePreferences,
} = require("../src/preferences.js");

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  const calls = { get: 0, set: 0, remove: 0 };
  return {
    calls,
    getItem(key) {
      calls.get += 1;
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      calls.set += 1;
      values.set(key, value);
    },
    removeItem(key) {
      calls.remove += 1;
      values.delete(key);
    },
    value(key) {
      return values.get(key);
    },
  };
}

const allowed = {
  profiles: ["overallEfficiency", "kit"],
  ages: ["VirtualFuture", "SpaceAgeSpaceHub"],
  categories: ["All Building Categories", "CARE 2026 Event Rewards"],
  searchModes: ["building", "fragment"],
  qiRoles: ["Both", "Blue", "Red"],
  strengths: ["combat", "kit-oneUp"],
  topNs: ["50", "200", "all"],
  weightModes: ["default", "custom"],
  weightProfiles: ["overall", "kits"],
  attributeKeys: ["boost_attack", "prod_kit_one_up"],
  sortKeys: ["profile", "name", "score"],
};

test("preference store reads the current schema", () => {
  const values = { profile: "kit", age: "VirtualFuture" };
  const storage = memoryStorage({
    [STORAGE_KEY]: JSON.stringify({ schemaVersion: SCHEMA_VERSION, savedAt: "2026-07-15T00:00:00Z", values }),
  });
  const store = createPreferenceStore(storage);

  assert.deepEqual(store.read(), values);
  assert.equal(store.save(values), "unchanged");
  assert.equal(storage.calls.set, 0);
});

test("preference store ignores malformed and outdated data", () => {
  const malformed = memoryStorage({ [STORAGE_KEY]: "not json" });
  assert.equal(createPreferenceStore(malformed).read(), null);

  const outdated = memoryStorage({
    [STORAGE_KEY]: JSON.stringify({ schemaVersion: SCHEMA_VERSION + 1, values: { profile: "kit" } }),
  });
  assert.equal(createPreferenceStore(outdated).read(), null);
});

test("preference store writes only changed snapshots and clears safely", () => {
  const storage = memoryStorage();
  const store = createPreferenceStore(storage);
  const values = { profile: "kit", searchMode: "fragment" };

  store.remember(values);
  assert.equal(store.save(values), "unchanged");
  assert.equal(store.save({ ...values, profile: "overallEfficiency" }), "saved");
  assert.equal(store.save({ ...values, profile: "overallEfficiency" }), "unchanged");
  assert.equal(storage.calls.set, 1);

  const envelope = JSON.parse(storage.value(STORAGE_KEY));
  assert.equal(envelope.schemaVersion, SCHEMA_VERSION);
  assert.deepEqual(envelope.values, { ...values, profile: "overallEfficiency" });
  assert.equal(store.clear(), "cleared");
  assert.equal(storage.calls.remove, 1);
});

test("storage failures never escape into the dashboard", () => {
  const brokenStorage = {
    getItem() { throw new Error("blocked"); },
    setItem() { throw new Error("quota"); },
    removeItem() { throw new Error("blocked"); },
  };
  const store = createPreferenceStore(brokenStorage);

  assert.equal(store.read(), null);
  assert.equal(store.save({ profile: "kit" }), "error");
  assert.equal(store.clear(), "error");
});

test("sanitizer keeps valid settings and removes untrusted values", () => {
  const sanitized = sanitizePreferences({
    profile: "kit",
    age: "VirtualFuture",
    category: "CARE 2026 Event Rewards",
    searchMode: "fragment",
    qiRole: "Both",
    focus: { gbgGe: 1, redBlue: 6, attackDefense: 3.5, unitAge: 5, fpGoods: 3 },
    production: { fp: 30000, goods: -1, guildGoods: 20000, medals: Infinity, specialGoods: 120 },
    filters: {
      strengths: ["combat", "unknown", "combat", "kit-oneUp"],
      minArea: 2,
      maxArea: 20,
      noRoadOnly: true,
      topN: "all",
    },
    weightMode: "custom",
    customWeights: {
      overall: { boost_attack: 2.5, unknown: 999 },
      kits: { prod_kit_one_up: 7, boost_attack: 1.5 },
      __proto__: { boost_attack: 10 },
    },
    sort: { key: "name", dir: "asc" },
    search: "This must never be persisted",
  }, allowed);

  assert.deepEqual(sanitized, {
    profile: "kit",
    age: "VirtualFuture",
    category: "CARE 2026 Event Rewards",
    searchMode: "fragment",
    qiRole: "Both",
    focus: { gbgGe: 1, unitAge: 5, fpGoods: 3 },
    production: { fp: 30000, guildGoods: 20000, specialGoods: 120 },
    filters: {
      strengths: ["combat", "kit-oneUp"],
      minArea: 2,
      maxArea: 20,
      noRoadOnly: true,
      topN: "all",
    },
    weightMode: "custom",
    customWeights: {
      overall: { boost_attack: 2.5 },
      kits: { prod_kit_one_up: 7 },
    },
    sort: { key: "name", dir: "asc" },
  });
  assert.equal("search" in sanitized, false);
});

test("sanitizer rejects an inverted area range and invalid sorting", () => {
  const sanitized = sanitizePreferences({
    filters: { minArea: 20, maxArea: 2, noRoadOnly: false, topN: "5000" },
    sort: { key: "constructor", dir: "sideways" },
    customWeights: { kits: { prod_kit_one_up: 11 } },
  }, allowed);

  assert.deepEqual(sanitized, {
    filters: { noRoadOnly: false },
    customWeights: { kits: {} },
  });
});
