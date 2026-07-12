const DATA = window.FOE_BUILDING_RANKING_DATA;
const ALL_CATEGORIES = "All Building Categories";
const PRESET_PROFILES_ENABLED = false;

const PROFILE_CONFIG = {
  overallEfficiency: {
    title: "Overall Efficiency",
    subtitle: "Best for finding well-rounded buildings that give strong value for their space. It uses the Overall score, then divides by adjusted area. A building that needs a road counts as using one extra tile.",
    weightProfile: "overall",
    efficiency: true,
  },
  overall: {
    title: "Overall",
    subtitle: "An all-round comparison of production, combat, Quantum Incursions, units, and other useful benefits. Building size is not part of this score, so choose Overall Efficiency when space matters.",
    weightProfile: "overall",
    efficiency: false,
  },
  fighting: {
    title: "Fighting Ranking",
    subtitle: "Ranks buildings for combat using your Guild Battlegrounds versus Guild Expedition, red versus blue, attack versus defense, and unit-age choices. Building size is not part of this score.",
    weightProfile: "fighting",
    efficiency: false,
  },
  fightingEfficiency: {
    title: "Fighting Efficiency",
    subtitle: "Uses the same combat priorities as Fighting Ranking, but favors buildings that provide more combat value per tile. A required road adds one tile to the area.",
    weightProfile: "fighting",
    efficiency: true,
  },
  farming: {
    title: "Farming Ranking",
    subtitle: "Compares resource-producing buildings using Forge Points, Goods Total, medals, net happiness, blueprints, diamonds, and supplies. This profile is still being tuned, especially for goods and diamonds, so treat it as a guide and adjust the weights when needed.",
    weightProfile: "farming",
    efficiency: false,
  },
  farmingEfficiency: {
    title: "Farming Efficiency",
    subtitle: "Shows the Farming value delivered per tile, with one extra tile for a required road. The Farming model is still being tuned, especially for goods and diamonds, so treat the results as a guide.",
    weightProfile: "farming",
    efficiency: true,
  },
  qi: {
    title: "QI Ranking",
    subtitle: "Ranks buildings for Quantum Incursions using combat bonuses, action points, and starting resources. The QI fighter role decides whether blue, red, or both combat bonuses receive value.",
    weightProfile: "qi",
    efficiency: false,
  },
  qiEfficiency: {
    title: "QI Efficiency",
    subtitle: "Shows Quantum Incursions value per tile using your selected QI fighter role. A building that needs a road counts as using one extra tile.",
    weightProfile: "qi",
    efficiency: true,
  },
  kit: {
    title: "Kit Producers",
    subtitle: "Compares expected production of seven useful kit families. Fragment rewards are converted to completed-kit equivalents, supply rushes include their duration, and building size is not part of this score.",
    weightProfile: "kits",
    efficiency: false,
  },
  kitEfficiency: {
    title: "Kit Efficiency",
    subtitle: "Uses the same kit-production score as Kit Producers, then divides it by adjusted area. A required road adds one tile to the area.",
    weightProfile: "kits",
    efficiency: true,
  },
};

const PRESETS = {
  balanced: {
    profile: "overallEfficiency",
    values: { gbgGeFocus: 3, redBlueFocus: 3, attackDefenseFocus: 3, unitAgeFocus: 3, fpGoodsFocus: 3, qiRole: "Both" },
  },
  space: {
    profile: "overallEfficiency",
    values: { gbgGeFocus: 3, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 2, qiRole: "Both" },
  },
  gbg: {
    profile: "fightingEfficiency",
    values: { gbgGeFocus: 1, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 2, qiRole: "Both" },
  },
  ge: {
    profile: "fightingEfficiency",
    values: { gbgGeFocus: 5, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 2, qiRole: "Both" },
  },
  qi: {
    profile: "qiEfficiency",
    values: { gbgGeFocus: 3, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 2, qiRole: "Both" },
  },
  fp: {
    profile: "farming",
    values: { gbgGeFocus: 3, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 1, qiRole: "Both" },
  },
  goods: {
    profile: "farming",
    values: { gbgGeFocus: 3, redBlueFocus: 3, attackDefenseFocus: 2, unitAgeFocus: 3, fpGoodsFocus: 5, qiRole: "Both" },
  },
};

const state = {
  profile: "overallEfficiency",
  rows: [],
  selectedAgeRows: [],
  activeDetailEntityId: null,
  detailSelectedAttributeKey: null,
  detailReturnFocus: null,
  sort: { key: "profile", dir: "desc" },
  detailSort: { key: "score", dir: "desc" },
  suppressUrlUpdate: false,
  customWeights: {
    overall: {},
    fighting: {},
    farming: {},
    qi: {},
    kits: {},
  },
};

const focusLabels = {
  gbgGeFocus: ["GBG", "GE"],
  redBlueFocus: ["Red", "Blue"],
  attackDefenseFocus: ["Attack", "Defense"],
  unitAgeFocus: ["Current age units", "Next age units"],
  fpGoodsFocus: ["FP", "Goods"],
};

const STRENGTH_INFO = {
  Combat: { cls: "combat", description: "Attack, defense, or unit value that is not tied to one specific game mode." },
  GBG: { cls: "gbg", description: "Useful combat bonuses for Guild Battlegrounds." },
  GE: { cls: "ge", description: "Useful combat bonuses for Guild Expedition." },
  QI: { cls: "qi", description: "Quantum Incursions combat bonuses, action points, or starting resources." },
  FP: { cls: "fp", description: "Produces Forge Points or increases your Forge Point production." },
  Goods: { cls: "goods", description: "Produces regular or guild goods, or increases goods production." },
  Prod: { cls: "prod", description: "Other useful production, such as medals or supplies." },
  City: { cls: "utility", description: "Supports your city with happiness or population." },
  Diamond: { cls: "diamond", description: "Produces diamonds." },
  Blueprint: { cls: "blueprint", description: "Produces Great Building blueprints." },
  "One-Up": { cls: "kit", description: "Produces One-Up Kit fragments or completed kits." },
  Renovation: { cls: "kit", description: "Produces Renovation Kit fragments or completed kits." },
  FSP: { cls: "kit", description: "Produces Finish Special Production rewards." },
  "Supply Finish": { cls: "kit", description: "Produces timed or all-supply production rush rewards." },
  "Goods Finish": { cls: "kit", description: "Produces rewards that finish a goods-building production." },
  "Mass Aid": { cls: "kit", description: "Produces Mass Self-Aid Kit fragments or completed kits." },
  Store: { cls: "kit", description: "Produces Store Building fragments or completed kits." },
};

const KIT_FAMILIES = DATA.kitFamilies || [];
const KIT_FAMILY_BY_KEY = Object.fromEntries(KIT_FAMILIES.map((family) => [family.key, family]));

const el = {
  appStatus: document.getElementById("appStatus"),
  versionLabel: document.getElementById("versionLabel"),
  presetSelect: document.getElementById("presetSelect"),
  ageSelect: document.getElementById("ageSelect"),
  categorySelect: document.getElementById("categorySelect"),
  categorySelectionPreview: document.getElementById("categorySelectionPreview"),
  searchInput: document.getElementById("searchInput"),
  shareButton: document.getElementById("shareButton"),
  settingsSummaryText: document.getElementById("settingsSummaryText"),
  baseProductionControls: document.getElementById("baseProductionControls"),
  focusControls: document.getElementById("focusControls"),
  qiRoleSelect: document.getElementById("qiRoleSelect"),
  gbgGeFocus: document.getElementById("gbgGeFocus"),
  redBlueFocus: document.getElementById("redBlueFocus"),
  attackDefenseFocus: document.getElementById("attackDefenseFocus"),
  unitAgeFocus: document.getElementById("unitAgeFocus"),
  fpGoodsFocus: document.getElementById("fpGoodsFocus"),
  gbgGeValue: document.getElementById("gbgGeValue"),
  redBlueValue: document.getElementById("redBlueValue"),
  attackDefenseValue: document.getElementById("attackDefenseValue"),
  unitAgeValue: document.getElementById("unitAgeValue"),
  fpGoodsValue: document.getElementById("fpGoodsValue"),
  fpEstimate: document.getElementById("fpEstimate"),
  goodsEstimate: document.getElementById("goodsEstimate"),
  guildGoodsEstimate: document.getElementById("guildGoodsEstimate"),
  medalEstimate: document.getElementById("medalEstimate"),
  specialGoodsEstimate: document.getElementById("specialGoodsEstimate"),
  strengthFilter: document.getElementById("strengthFilter"),
  minAreaFilter: document.getElementById("minAreaFilter"),
  maxAreaFilter: document.getElementById("maxAreaFilter"),
  areaFilterError: document.getElementById("areaFilterError"),
  noRoadFilter: document.getElementById("noRoadFilter"),
  topNSelect: document.getElementById("topNSelect"),
  weightModeSelect: document.getElementById("weightModeSelect"),
  customWeights: document.getElementById("customWeights"),
  resetWeightsButton: document.getElementById("resetWeightsButton"),
  rankingBody: document.getElementById("rankingBody"),
  strengthLegend: document.getElementById("strengthLegend"),
  emptyState: document.getElementById("emptyState"),
  rankingTitle: document.getElementById("rankingTitle"),
  rankingSubtitle: document.getElementById("rankingSubtitle"),
  rankingDescription: document.getElementById("rankingDescription"),
  scoreColumnLabel: document.getElementById("scoreColumnLabel"),
  efficiencyColumnLabel: document.getElementById("efficiencyColumnLabel"),
  activeFilters: document.getElementById("activeFilters"),
  resultMeta: document.getElementById("resultMeta"),
  summaryGrid: document.getElementById("summaryGrid"),
  resetButton: document.getElementById("resetButton"),
  detailDrawer: document.getElementById("detailDrawer"),
  drawerBackdrop: document.getElementById("drawerBackdrop"),
  detailContent: document.getElementById("detailContent"),
  closeDrawer: document.getElementById("closeDrawer"),
  compareA: document.getElementById("compareA"),
  compareB: document.getElementById("compareB"),
  buildingList: document.getElementById("buildingList"),
  compareOutput: document.getElementById("compareOutput"),
};

let renderTimer = null;
let pendingAfterRender = null;
let announceTimer = null;

function fmt(value, digits = 2) {
  if (!Number.isFinite(value)) return "";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function fmtCompact(value, digits = 2) {
  if (!Number.isFinite(value)) return "";
  return value.toLocaleString(undefined, {
    maximumFractionDigits: digits,
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function numberValue(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function customWeightRules(profile) {
  return profile === "kits"
    ? { min: 0, max: 10, step: 1, integer: true }
    : { min: 0, max: 1000, step: 0.1, integer: false };
}

function sanitizeCustomWeight(profile, value) {
  const rules = customWeightRules(profile);
  const numeric = numberValue(value);
  const normalized = rules.integer ? Math.round(numeric) : numeric;
  return clamp(normalized, rules.min, rules.max);
}

function sanitizeCustomWeightState(value) {
  const profiles = ["overall", "fighting", "farming", "qi", "kits"];
  const sanitized = Object.fromEntries(profiles.map((profile) => [profile, {}]));
  for (const profile of profiles) {
    const weights = value?.[profile];
    if (!weights || typeof weights !== "object" || Array.isArray(weights)) continue;
    for (const [key, weight] of Object.entries(weights)) {
      if (!Number.isFinite(Number(weight))) continue;
      sanitized[profile][key] = sanitizeCustomWeight(profile, weight);
    }
  }
  return sanitized;
}

function announce(message) {
  window.clearTimeout(announceTimer);
  el.appStatus.textContent = "";
  window.requestAnimationFrame(() => {
    el.appStatus.textContent = message;
    announceTimer = window.setTimeout(() => {
      el.appStatus.textContent = "";
    }, 3000);
  });
}

function ageLabel(ageKey) {
  return DATA.ages.find((age) => age.key === ageKey)?.label || ageKey;
}

function presetLabel(value) {
  return Array.from(el.presetSelect.options).find((option) => option.value === value)?.textContent || value;
}

function sortLabel() {
  const labels = {
    profile: PROFILE_CONFIG[state.profile].efficiency ? "profile efficiency" : "profile score",
    name: "building name",
    score: "score",
    efficiency: "efficiency",
    area: "area",
  };
  return `${labels[state.sort.key] || state.sort.key}, ${state.sort.dir === "asc" ? "ascending" : "descending"}`;
}

function focusValueText(value, leftLabel, rightLabel) {
  if (value === 1) return `${leftLabel} only`;
  if (value === 2) return `${leftLabel} heavy`;
  if (value === 4) return `${rightLabel} heavy`;
  if (value === 5) return `${rightLabel} only`;
  return "Balanced";
}

function controls() {
  return {
    age: el.ageSelect.value,
    category: el.categorySelect.value,
    search: el.searchInput.value.trim().toLowerCase(),
    qiRole: el.qiRoleSelect.value,
    gbgGeFocus: numberValue(el.gbgGeFocus.value),
    redBlueFocus: numberValue(el.redBlueFocus.value),
    attackDefenseFocus: numberValue(el.attackDefenseFocus.value),
    unitAgeFocus: numberValue(el.unitAgeFocus.value),
    fpGoodsFocus: numberValue(el.fpGoodsFocus.value),
    estimatedFpProduction: numberValue(el.fpEstimate.value),
    estimatedGoodsProduction: numberValue(el.goodsEstimate.value),
    estimatedGuildGoodsProduction: numberValue(el.guildGoodsEstimate.value),
    estimatedMedalProduction: numberValue(el.medalEstimate.value),
    estimatedSpecialGoodsProduction: numberValue(el.specialGoodsEstimate.value),
    strength: el.strengthFilter.value,
    minArea: el.minAreaFilter.value === "" ? null : numberValue(el.minAreaFilter.value),
    maxArea: el.maxAreaFilter.value === "" ? null : numberValue(el.maxAreaFilter.value),
    noRoadOnly: el.noRoadFilter.checked,
    topN: el.topNSelect.value,
  };
}

function areaFilterValidation(c = controls()) {
  const minEntered = el.minAreaFilter.value !== "";
  const maxEntered = el.maxAreaFilter.value !== "";
  if ((minEntered && !el.minAreaFilter.validity.valid) || (maxEntered && !el.maxAreaFilter.validity.valid)) {
    return {
      message: "Use whole area values of zero or more. Area filters are paused until this is corrected.",
      minInvalid: minEntered && !el.minAreaFilter.validity.valid,
      maxInvalid: maxEntered && !el.maxAreaFilter.validity.valid,
    };
  }
  if (c.minArea !== null && c.maxArea !== null && c.minArea > c.maxArea) {
    return {
      message: "Minimum area cannot be greater than maximum area. Area filters are paused until this is corrected.",
      minInvalid: true,
      maxInvalid: true,
    };
  }
  return { message: "", minInvalid: false, maxInvalid: false };
}

function syncLongValuePresentation() {
  const category = el.categorySelect.selectedOptions[0]?.textContent || el.categorySelect.value;
  const age = el.ageSelect.selectedOptions[0]?.textContent || el.ageSelect.value;
  el.categorySelect.title = category;
  el.ageSelect.title = age;
  el.categorySelectionPreview.textContent = category ? `Selected: ${category}` : "";
  el.categorySelectionPreview.hidden = category.length <= 30;
  el.compareA.title = el.compareA.value;
  el.compareB.title = el.compareB.value;
}

function attrInfo(key) {
  return DATA.attrs[key] || {};
}

function attrLabel(key) {
  return attrInfo(key).label || key;
}

function isKitProfile(profile = state.profile) {
  return PROFILE_CONFIG[profile]?.weightProfile === "kits";
}

function kitFamilyForAttr(key) {
  const family = attrInfo(key).kitFamily;
  return family ? KIT_FAMILY_BY_KEY[family] : null;
}

function recordHasKitProduction(record) {
  return KIT_FAMILIES.some((family) => rawAttr(record, family.attrKey) > 0);
}

function kitProductionForRecord(record) {
  const entry = DATA.kitProductionByEntity?.[record.entityId];
  if (!entry) return {};
  if (entry.overrides && Object.prototype.hasOwnProperty.call(entry.overrides, record.selectedAge)) {
    return entry.overrides[record.selectedAge] || {};
  }
  return entry.default || {};
}

function rawAttr(record, key) {
  return Number(record.attrs[key] || 0);
}

function effectiveAttrValue(record, key, c) {
  const constants = DATA.constants;
  const base = rawAttr(record, key);
  if (key === constants.prodFpAttr) {
    return base + rawAttr(record, constants.boostFpAttr) * c.estimatedFpProduction / 100;
  }
  if (key === constants.prodGoodsAttr) {
    return (
      base
      + rawAttr(record, constants.boostGoodsAttr) * c.estimatedGoodsProduction / 100
      + rawAttr(record, constants.boostSpecialGoodsAttr) * c.estimatedSpecialGoodsProduction / 100
    );
  }
  if (key === constants.prodGuildGoodsAttr) {
    return base + rawAttr(record, constants.boostGuildGoodsAttr) * c.estimatedGuildGoodsProduction / 100;
  }
  if (key === constants.prodMedalsAttr) {
    return base + rawAttr(record, constants.boostMedalsAttr) * c.estimatedMedalProduction / 100;
  }
  return base;
}

function directionFor(key) {
  return attrInfo(key).direction || "Higher";
}

function normalizeValue(key, value, min, max) {
  if (Math.abs(max - min) < 1e-12) return 0;
  if (attrInfo(key).isSignedCentered) {
    const scale = Math.max(Math.abs(min), Math.abs(max));
    return scale ? value / scale * 100 : 0;
  }
  if (directionFor(key) === "Lower") {
    return (max - value) / (max - min) * 100;
  }
  return (value - min) / (max - min) * 100;
}

function maxAnchor(key, c) {
  const constants = DATA.constants;
  if (key === constants.prodFpAttr) return c.estimatedFpProduction;
  if (key === constants.prodGoodsAttr) return c.estimatedGoodsProduction;
  if (key === constants.prodGuildGoodsAttr) return c.estimatedGuildGoodsProduction;
  if (key === constants.prodMedalsAttr) return c.estimatedMedalProduction;
  return null;
}

function computeStats(records, c) {
  const stats = {};
  for (const key of DATA.attrKeys) {
    let min = Infinity;
    let max = -Infinity;
    for (const record of records) {
      const value = effectiveAttrValue(record, key, c);
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
    if (!Number.isFinite(min)) min = 0;
    if (!Number.isFinite(max)) max = 0;
    const anchor = maxAnchor(key, c);
    if (anchor !== null) max = Math.max(max, anchor);
    stats[key] = { min, max };
  }
  return stats;
}

function focusLeft(focus) {
  return clamp((5 - focus) / 4, 0, 1);
}

function focusRight(focus) {
  return clamp((focus - 1) / 4, 0, 1);
}

function splitFocusWeight(combined, focus) {
  const safeFocus = clamp(focus, 1, 5);
  const half = combined / 2;
  if (safeFocus <= 3) {
    return {
      left: combined - (safeFocus - 1) / 2 * half,
      right: half * (safeFocus - 1) / 2,
    };
  }
  return {
    left: half * (5 - safeFocus) / 2,
    right: half + (safeFocus - 3) / 2 * half,
  };
}

function overallGbgBudget(focus) {
  const budgets = DATA.constants.overallFightingSubgroupBudgets;
  const defaultBudget = budgets["Fighting: GBG"];
  const combined = DATA.constants.overallGbgGeCombinedBudget;
  const safeFocus = clamp(focus, 1, 5);
  if (safeFocus <= 3) return defaultBudget + (3 - safeFocus) / 2 * (combined - defaultBudget);
  return defaultBudget * (5 - safeFocus) / 2;
}

function overallGeBudget(focus) {
  const budgets = DATA.constants.overallFightingSubgroupBudgets;
  const defaultBudget = budgets["Fighting: GE"];
  const combined = DATA.constants.overallGbgGeCombinedBudget;
  const safeFocus = clamp(focus, 1, 5);
  if (safeFocus >= 3) return defaultBudget + (safeFocus - 3) / 2 * (combined - defaultBudget);
  return defaultBudget * (safeFocus - 1) / 2;
}

function groupBudget(group, c) {
  const budgets = DATA.constants.overallFightingSubgroupBudgets;
  if (group === "Fighting: GBG") return overallGbgBudget(c.gbgGeFocus);
  if (group === "Fighting: GE") return overallGeBudget(c.gbgGeFocus);
  return budgets[group] ?? DATA.constants.overallNonFightingBudget;
}

function qiRoleOverallMultiplier(info, c) {
  if (info.isQiBlue) {
    if (c.qiRole === "Blue") return 1;
    if (c.qiRole === "Both") return 8 / 15;
    return 0;
  }
  if (info.isQiRed) {
    if (c.qiRole === "Red") return 1;
    if (c.qiRole === "Both") return 8 / 15;
    return 0;
  }
  return 1;
}

function productionRawWeights(c, combined) {
  const split = splitFocusWeight(combined, c.fpGoodsFocus);
  return { fp: split.left, goods: split.right };
}

function overallRawWeight(key, c) {
  const info = attrInfo(key);
  const constants = DATA.constants;
  if (info.isForcedZero || info.isGoodsTotalComponent || info.isKit) return 0;
  let weight;
  if (key === constants.prodFpAttr) {
    const combined = attrInfo(constants.prodFpAttr).defaultWeight + attrInfo(constants.prodGoodsAttr).defaultWeight;
    weight = productionRawWeights(c, combined).fp;
  } else if (key === constants.prodGoodsAttr) {
    const combined = attrInfo(constants.prodFpAttr).defaultWeight + attrInfo(constants.prodGoodsAttr).defaultWeight;
    weight = productionRawWeights(c, combined).goods;
  } else if (key === "prod_unit_current_age") {
    weight = (attrInfo("prod_unit_rogue").defaultWeight || 0) * focusLeft(c.unitAgeFocus);
  } else if (key === "prod_unit_next_age") {
    weight = (attrInfo("prod_unit_rogue").defaultWeight || 0) * focusRight(c.unitAgeFocus);
  } else if (info.isOverallQiStart) {
    weight = constants.overallQiStartRawWeight;
  } else if (key === constants.prodGuildGoodsAttr) {
    weight = (attrInfo(constants.prodGoodsAttr).defaultWeight || 0) / 5;
  } else {
    weight = info.defaultWeight || 0;
  }
  if (!weight) return 0;
  if (info.isGbg) weight *= focusLeft(c.gbgGeFocus);
  else if (info.isGe) weight *= focusRight(c.gbgGeFocus);
  if (info.isRed) weight *= focusLeft(c.redBlueFocus);
  else if (info.isBlue) weight *= focusRight(c.redBlueFocus);
  if (info.isAttack) weight *= focusLeft(c.attackDefenseFocus);
  else if (info.isDefense) weight *= focusRight(c.attackDefenseFocus);
  weight *= qiRoleOverallMultiplier(info, c);
  return weight;
}

function overallWeights(c) {
  const raw = {};
  const totals = {};
  for (const key of DATA.attrKeys) {
    raw[key] = overallRawWeight(key, c);
    const group = attrInfo(key).overallGroup || "Non-Fighting";
    totals[group] = (totals[group] || 0) + Math.abs(raw[key]);
  }
  const out = {};
  for (const key of DATA.attrKeys) {
    const group = attrInfo(key).overallGroup || "Non-Fighting";
    out[key] = raw[key] && totals[group] ? raw[key] * groupBudget(group, c) / totals[group] : 0;
  }
  return out;
}

function fightingWeight(key, c) {
  const info = attrInfo(key);
  const constants = DATA.constants;
  if (info.isForcedZero) return 0;
  if (key === "prod_unit_current_age") {
    return focusLeft(c.unitAgeFocus) * constants.fightingCurrentNextUnitCombinedRawWeight * constants.fightingWeightScale;
  }
  if (key === "prod_unit_next_age") {
    return focusRight(c.unitAgeFocus) * constants.fightingCurrentNextUnitCombinedRawWeight * constants.fightingWeightScale;
  }
  if (key === "prod_unit_rogue") return constants.fightingWeightScale;
  if (!info.isFighting) return 0;
  let weight = info.defaultWeight || 0;
  if (info.isGbg) {
    const base = attrInfo("boost_att_boost_attacker_battleground").defaultWeight || 1;
    weight *= constants.fightingGbgGeCombinedRawWeight * focusLeft(c.gbgGeFocus) / base;
  } else if (info.isGe) {
    const base = attrInfo("boost_att_boost_attacker_guild_expedition").defaultWeight || 1;
    weight *= constants.fightingGbgGeCombinedRawWeight * focusRight(c.gbgGeFocus) / base;
  }
  if (info.isRed) weight *= focusLeft(c.redBlueFocus);
  else if (info.isBlue) weight *= focusRight(c.redBlueFocus);
  if (info.isAttack) weight *= focusLeft(c.attackDefenseFocus);
  else if (info.isDefense) weight *= focusRight(c.attackDefenseFocus);
  return weight * constants.fightingWeightScale;
}

function farmingWeight(key, c) {
  const constants = DATA.constants;
  if (attrInfo(key).isForcedZero) return 0;
  if (key === constants.prodFpAttr) {
    return splitFocusWeight(constants.farmingFpGoodsCombinedRawWeight, c.fpGoodsFocus).left;
  }
  if (key === constants.prodGoodsAttr) {
    return splitFocusWeight(constants.farmingFpGoodsCombinedRawWeight, c.fpGoodsFocus).right;
  }
  return constants.farmingSecondaryRawWeights[key] || 0;
}

function qiWeight(key, c) {
  const label = attrLabel(key);
  if (!attrInfo(key).isQi || attrInfo(key).isForcedZero) return 0;
  if (label === "Boost: Att Boost: Blue QI") return c.qiRole === "Blue" ? 15 : c.qiRole === "Both" ? 8 : 0;
  if (label === "Boost: Def Boost: Blue QI") return c.qiRole === "Blue" ? 10.5 : c.qiRole === "Both" ? 5.6 : 0;
  if (label === "Boost: Att Boost: Red QI") return c.qiRole === "Red" ? 15 : c.qiRole === "Both" ? 8 : 0;
  if (label === "Boost: Def Boost: Red QI") return c.qiRole === "Red" ? 10.5 : c.qiRole === "Both" ? 5.6 : 0;
  if (label === "Boost: QI Action Points Collection All") return 20;
  if (label === "Boost: QI Action Points Capacity All") return 1;
  if (label === "Boost: QI Coins Start All") return 3;
  if (label === "Boost: QI Goods Start All") return 5;
  if (label === "Boost: QI Units Start All") return 5;
  return attrInfo(key).defaultWeight || 1;
}

function kitWeight(key) {
  return attrInfo(key).isKit ? 1 : 0;
}

function weightMap(profile, c) {
  if (profile === "overall") return overallWeights(c);
  const out = {};
  for (const key of DATA.attrKeys) {
    if (profile === "fighting") out[key] = fightingWeight(key, c);
    else if (profile === "farming") out[key] = farmingWeight(key, c);
    else if (profile === "qi") out[key] = qiWeight(key, c);
    else if (profile === "kits") out[key] = kitWeight(key);
  }
  return out;
}

function customizedWeightMap(profile, c) {
  const weights = weightMap(profile, c);
  if (el.weightModeSelect.value !== "custom") return weights;
  const overrides = state.customWeights[profile] || {};
  return Object.fromEntries(
    Object.entries(weights).map(([key, value]) => [
      key,
      isCustomizableWeight(profile, key) && Object.prototype.hasOwnProperty.call(overrides, key)
        ? sanitizeCustomWeight(profile, overrides[key])
        : value,
    ])
  );
}

function activeWeightProfile() {
  return PROFILE_CONFIG[state.profile].weightProfile;
}

function isCustomizableWeight(profile, key) {
  const info = attrInfo(key);
  const constants = DATA.constants;
  if (info.isForcedZero) return false;
  if (profile === "overall") return !info.isGoodsTotalComponent && !info.isKit;
  if (profile === "fighting") {
    return info.isFighting || key === "prod_unit_current_age" || key === "prod_unit_next_age" || key === "prod_unit_rogue";
  }
  if (profile === "farming") {
    return (
      key === constants.prodFpAttr
      || key === constants.prodGoodsAttr
      || Object.prototype.hasOwnProperty.call(constants.farmingSecondaryRawWeights, key)
    );
  }
  if (profile === "qi") return info.isQi;
  if (profile === "kits") return info.isKit;
  return false;
}

function customizableWeightRows(profile, c) {
  const defaults = weightMap(profile, c);
  return DATA.attrKeys
    .map((key) => ({
      key,
      label: attrLabel(key),
      defaultWeight: defaults[key] || 0,
      override: state.customWeights[profile]?.[key],
      group: attrInfo(key).isKit ? "Kit production" : attrInfo(key).overallGroup || "Non-Fighting",
    }))
    .filter((row) => isCustomizableWeight(profile, row.key) || row.override !== undefined)
    .sort((a, b) => Math.abs(b.defaultWeight) - Math.abs(a.defaultWeight) || a.label.localeCompare(b.label));
}

function scoreRecord(record, stats, weights, c) {
  let totalWeight = 0;
  let score = 0;
  const contributions = [];
  for (const key of DATA.attrKeys) {
    const weight = weights[key] || 0;
    if (!weight) continue;
    const stat = stats[key];
    const value = effectiveAttrValue(record, key, c);
    const normalized = normalizeValue(key, value, stat.min, stat.max);
    const points = normalized * weight;
    score += points;
    totalWeight += Math.abs(weight);
    if (Math.abs(points) > 1e-9 || Math.abs(value) > 1e-9) {
      contributions.push({
        key,
        label: attrLabel(key),
        value,
        normalized,
        weight,
        scorePoints: totalWeight ? points : 0,
      });
    }
  }
  const finalScore = totalWeight ? score / totalWeight : 0;
  contributions.forEach((item) => {
    item.scorePoints = totalWeight ? item.scorePoints / totalWeight : 0;
  });
  contributions.sort((a, b) => b.scorePoints - a.scorePoints);
  return { score: finalScore, contributions, totalWeight };
}

function strengthBadges(record, contributions) {
  const labels = [];
  const addBadge = (badge, cls) => {
    if (badge && !labels.some((existing) => existing.text === badge)) {
      labels.push({ text: badge, cls });
    }
  };

  if (isKitProfile()) {
    for (const item of contributions) {
      const family = kitFamilyForAttr(item.key);
      if (!family || item.value <= 0) continue;
      addBadge(family.strength, "kit");
      if (labels.length >= 3) break;
    }
    return labels;
  }

  if (rawAttr(record, "prod_resource_premium") > 0) addBadge("Diamond", "diamond");
  if (rawAttr(record, "prod_resource_blueprint") > 0) addBadge("Blueprint", "blueprint");

  for (const item of contributions) {
    if (labels.length >= 3) break;
    if (item.scorePoints <= 0.05) continue;
    const label = item.label;
    if (label.includes("QI")) {
      addBadge("QI", "qi");
    } else if (label.includes("Att Boost") || label.includes("Def Boost") || label.includes("Unit") || label.includes("Rogue")) {
      if (label.includes("Battleground")) {
        addBadge("GBG", "gbg");
      } else if (label.includes("Guild Expedition")) {
        addBadge("GE", "ge");
      } else {
        addBadge("Combat", "combat");
      }
    } else if (label.includes("FP") || label.includes("Goods") || label.includes("Medal") || label.includes("Supplies")) {
      if (label.includes("FP")) {
        addBadge("FP", "fp");
      } else if (label.includes("Goods")) {
        addBadge("Goods", "goods");
      } else {
        addBadge("Prod", "prod");
      }
    } else if (label.includes("Happiness") || label.includes("Population")) {
      addBadge("City", "utility");
    }
  }
  return labels;
}

function rowHasStrength(row, strength) {
  if (!strength) return true;
  const requestedKitFamily = strength.startsWith("kit-") ? strength.slice(4) : "";
  return Object.entries(row.record.attrs).some(([key, value]) => {
    if (Number(value || 0) <= 0) return false;
    const info = attrInfo(key);
    const label = attrLabel(key);
    if (requestedKitFamily) return info.kitFamily === requestedKitFamily;
    if (strength === "combat") return info.isFighting;
    if (strength === "qi") return info.isQi || label.includes("QI");
    if (strength === "fp") return key === DATA.constants.prodFpAttr || label.includes("FP");
    if (strength === "goods") return key === DATA.constants.prodGoodsAttr || key === DATA.constants.prodGuildGoodsAttr || label.includes("Goods");
    if (strength === "units") return key.startsWith("prod_unit") || label.includes("Unit") || label.includes("Rogue");
    if (strength === "diamonds") return key === "prod_resource_premium" || label.includes("Diamond");
    if (strength === "blueprints") return key === "prod_resource_blueprint" || label.includes("Blueprint");
    return true;
  });
}

function buildRows() {
  const c = controls();
  const config = PROFILE_CONFIG[state.profile];
  const records = DATA.recordsByAge[c.age] || [];
  state.selectedAgeRows = records;
  const stats = computeStats(records, c);
  const weights = customizedWeightMap(config.weightProfile, c);
  let rows = records.map((record) => {
    const scored = scoreRecord(record, stats, weights, c);
    const efficiency = record.adjustedArea ? scored.score / record.adjustedArea : 0;
    return {
      record,
      score: scored.score,
      efficiency,
      rankValue: config.efficiency ? efficiency : scored.score,
      contributions: scored.contributions,
      totalWeight: scored.totalWeight,
      badges: strengthBadges(record, scored.contributions),
    };
  });
  if (isKitProfile()) rows = rows.filter((row) => recordHasKitProduction(row.record));
  rows.sort((a, b) => b.rankValue - a.rankValue || a.record.name.localeCompare(b.record.name));
  rows.forEach((row, idx) => { row.rank = idx + 1; });
  state.rows = rows;
  return rows;
}

function filteredRows(rows) {
  const c = controls();
  const areaFiltersValid = !areaFilterValidation(c).message;
  return rows.filter((row) => {
    if (c.category !== ALL_CATEGORIES && row.record.category !== c.category) return false;
    if (c.search && !row.record.name.toLowerCase().includes(c.search)) return false;
    if (areaFiltersValid && c.minArea !== null && row.record.adjustedArea < c.minArea) return false;
    if (areaFiltersValid && c.maxArea !== null && row.record.adjustedArea > c.maxArea) return false;
    if (c.noRoadOnly && row.record.requiresRoad) return false;
    if (!rowHasStrength(row, c.strength)) return false;
    return true;
  });
}

function displayRows(rows) {
  const filtered = filteredRows(rows);
  const sorted = [...filtered];
  const direction = state.sort.dir === "asc" ? 1 : -1;
  sorted.sort((a, b) => {
    let aValue;
    let bValue;
    if (state.sort.key === "name") {
      return a.record.name.localeCompare(b.record.name) * direction;
    }
    if (state.sort.key === "score") {
      aValue = a.score;
      bValue = b.score;
    } else if (state.sort.key === "efficiency") {
      aValue = a.efficiency;
      bValue = b.efficiency;
    } else if (state.sort.key === "area") {
      aValue = a.record.adjustedArea || 0;
      bValue = b.record.adjustedArea || 0;
    } else {
      aValue = a.rankValue;
      bValue = b.rankValue;
    }
    return (aValue - bValue) * direction || a.record.name.localeCompare(b.record.name);
  });
  return sorted;
}

function renderSummary(rows) {
  const c = controls();
  const config = PROFILE_CONFIG[state.profile];
  const kitProfile = isKitProfile();
  const filtered = filteredRows(rows);
  const top = filtered[0];
  el.summaryGrid.innerHTML = [
    [kitProfile ? "Kit producers" : "Buildings", filtered.length.toLocaleString(), kitProfile
      ? "The number of buildings with supported kit production left after your current search and filters."
      : "The number of buildings left after your current search and filters."],
    ["Top building", top ? top.record.name : "None", "The highest-ranked building among the current matches. Filters narrow the list but do not recalculate its rank."],
    [kitProfile ? "Top kit score" : "Top score", top ? fmt(top.score) : "", config.efficiency
      ? "The profile score of the efficiency winner. Another building may have a higher score before space is considered."
      : kitProfile
        ? "A comparison score across the seven supported kit families. It is not a literal number of kits produced."
        : "The active profile score of the top building. This is a comparison number, not an amount produced in the game."],
    [kitProfile ? "Kit efficiency" : "Top efficiency", top ? fmt(top.efficiency, 3) : "", config.efficiency
      ? "The top building's score per adjusted tile, including one extra tile when a road is required."
      : "The efficiency of the top-ranked building. Choose an Efficiency tab to rank buildings by value per tile."],
  ].map(([label, value, help], index) => `
    <div class="summary-card">
      <div class="summary-label-row">
        <span>${label}</span>
        <button class="info-button compact-info-button" type="button" aria-expanded="false" aria-controls="summaryInfo${index}" aria-label="Show ${label} information" data-info-label="${label}">i</button>
      </div>
      <strong>${escapeHtml(value)}</strong>
      <p id="summaryInfo${index}" class="summary-help info-text" hidden>${help}</p>
    </div>
  `).join("");
  el.rankingSubtitle.textContent = `${DATA.ages.find((age) => age.key === c.age)?.label || c.age} · ${c.category}`;
}

function renderTable(rows) {
  const config = PROFILE_CONFIG[state.profile];
  el.rankingTitle.textContent = config.title;
  const c = controls();
  const sorted = displayRows(rows);
  const limit = c.topN === "all" ? sorted.length : Number(c.topN);
  const visible = sorted.slice(0, limit);
  el.emptyState.textContent = isKitProfile()
    ? "No kit-producing buildings match the current filters."
    : "No buildings match the current filters.";
  el.emptyState.hidden = visible.length > 0;
  el.rankingBody.innerHTML = visible.map((row) => {
    const badges = row.badges.map((badge) => {
      const description = STRENGTH_INFO[badge.text]?.description || "A leading strength for this building in the active profile.";
      return `<span class="badge ${badge.cls}" title="${escapeHtml(description)}" aria-label="${escapeHtml(`${badge.text}: ${description}`)}">${badge.text}</span>`;
    }).join("");
    return `
      <tr data-entity-id="${row.record.entityId}">
        <td class="rank">${row.rank}</td>
        <td>
          <div class="building-name">${escapeHtml(row.record.name)}</div>
          <div class="building-meta">${escapeHtml(row.record.category)}</div>
        </td>
        <td>${fmt(row.score)}</td>
        <td>${fmt(row.efficiency, 3)}</td>
        <td>${row.record.adjustedArea || ""}</td>
        <td><div class="badges">${badges}</div></td>
        <td><button class="details-button" type="button">View</button></td>
      </tr>
    `;
  }).join("");
}

function renderBuildingList() {
  el.buildingList.innerHTML = state.selectedAgeRows
    .map((record) => `<option value="${escapeHtml(record.name)}"></option>`)
    .join("");
}

function renderStrengthLegend() {
  el.strengthLegend.innerHTML = `
    <p class="strength-legend-intro">Strength badges are quick highlights, not a complete list. Up to three appear in each row; open <strong>View</strong> to see the full scoring breakdown.</p>
    <div class="strength-legend-grid">
      ${Object.entries(STRENGTH_INFO).map(([label, info]) => `
        <div class="strength-legend-item">
          <span class="badge ${info.cls}">${label}</span>
          <span>${info.description}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function filterChips(c) {
  const chips = [];
  const areaValidation = areaFilterValidation(c);
  if (PRESET_PROFILES_ENABLED && el.presetSelect.value) chips.push(`Preset: ${presetLabel(el.presetSelect.value)}`);
  if (c.search) chips.push(`Search: ${el.searchInput.value.trim()}`);
  if (c.category !== ALL_CATEGORIES) chips.push(c.category);
  if (c.strength) chips.push(`Strength: ${el.strengthFilter.selectedOptions[0]?.textContent || c.strength}`);
  if (areaValidation.message) {
    chips.push("Area filters paused");
  } else {
    if (c.minArea !== null) chips.push(`Min area: ${c.minArea}`);
    if (c.maxArea !== null) chips.push(`Max area: ${c.maxArea}`);
  }
  if (c.noRoadOnly) chips.push("No road");
  if (el.weightModeSelect.value === "custom") chips.push("Custom weights");
  return chips;
}

function syncFocusOutputs() {
  const focusOutputs = [
    [el.gbgGeFocus, el.gbgGeValue, "gbgGeFocus"],
    [el.redBlueFocus, el.redBlueValue, "redBlueFocus"],
    [el.attackDefenseFocus, el.attackDefenseValue, "attackDefenseFocus"],
    [el.unitAgeFocus, el.unitAgeValue, "unitAgeFocus"],
    [el.fpGoodsFocus, el.fpGoodsValue, "fpGoodsFocus"],
  ];
  focusOutputs.forEach(([input, output, labelKey]) => {
    const value = numberValue(input.value);
    const [leftLabel, rightLabel] = focusLabels[labelKey];
    const label = focusValueText(value, leftLabel, rightLabel);
    output.textContent = label;
    input.setAttribute("aria-valuetext", label);
  });
}

function renderControlState(rows, visibleRows) {
  const c = controls();
  const kitProfile = isKitProfile();
  const areaValidation = areaFilterValidation(c);
  syncFocusOutputs();
  syncLongValuePresentation();

  el.baseProductionControls.hidden = kitProfile;
  el.focusControls.hidden = kitProfile;
  el.settingsSummaryText.textContent = kitProfile
    ? "City, kit priorities and filters"
    : "City, production, focus and filters";
  el.scoreColumnLabel.textContent = kitProfile ? "Kit score" : "Score";
  el.efficiencyColumnLabel.textContent = kitProfile ? "Kit efficiency" : "Efficiency";

  el.minAreaFilter.setAttribute("aria-invalid", areaValidation.minInvalid ? "true" : "false");
  el.maxAreaFilter.setAttribute("aria-invalid", areaValidation.maxInvalid ? "true" : "false");
  el.areaFilterError.textContent = areaValidation.message;
  el.areaFilterError.hidden = !areaValidation.message;

  syncProfileTabs();

  document.querySelectorAll(".sort-button").forEach((button) => {
    const active = button.dataset.sort === state.sort.key;
    button.classList.toggle("active-sort", active);
    button.closest("th")?.setAttribute(
      "aria-sort",
      active ? (state.sort.dir === "asc" ? "ascending" : "descending") : "none"
    );
    button.setAttribute(
      "aria-label",
      `${button.textContent.trim()} sort${active ? `, ${state.sort.dir === "asc" ? "ascending" : "descending"}` : ""}`
    );
  });

  el.rankingDescription.textContent = PROFILE_CONFIG[state.profile].subtitle;
  const chips = filterChips(c);
  el.activeFilters.innerHTML = chips.length
    ? chips.map((chip) => `<span class="filter-chip">${escapeHtml(chip)}</span>`).join("")
    : `<span class="filter-chip muted-chip">No filters</span>`;
  const limit = c.topN === "all" ? visibleRows.length : Math.min(Number(c.topN), visibleRows.length);
  el.resultMeta.textContent = `Showing ${limit.toLocaleString()} of ${visibleRows.length.toLocaleString()} matches · ${rows.length.toLocaleString()} total · Sorted by ${sortLabel()}`;
}

function renderCustomWeights() {
  const profile = activeWeightProfile();
  const rules = customWeightRules(profile);
  const kitProfile = profile === "kits";
  const c = controls();
  const rows = customizableWeightRows(profile, c);
  const activeCount = Object.keys(state.customWeights[profile] || {}).length;
  const totalWeight = rows.reduce((sum, row) => {
    const value = row.override !== undefined ? row.override : row.defaultWeight;
    return sum + Math.abs(value || 0);
  }, 0);
  el.customWeights.innerHTML = `
    <div class="custom-summary">
      <span>${PROFILE_CONFIG[state.profile].title}</span>
      <strong>${fmt(totalWeight, kitProfile ? 0 : 2)} importance total</strong>
    </div>
    <p class="section-note">${
      el.weightModeSelect.value === "custom"
        ? activeCount
          ? `${activeCount} custom change${activeCount === 1 ? " is" : "s are"} active for this profile. Every unchanged field still uses its default value.`
          : "Custom mode is on, but no values have been changed yet. Edit any field to create a custom value."
        : `Using the recommended weights for ${PROFILE_CONFIG[state.profile].title}. Choose Custom if you want to change the balance.`
    }</p>
    <p class="section-note">${kitProfile
      ? "Kit weights use whole numbers from 0 to 10. Zero ignores a kit family."
      : "Weights must be zero or greater. Zero ignores an attribute."
    }</p>
    <div class="weight-list">
      ${rows.map((row) => {
        const isChanged = row.override !== undefined && Math.abs((row.override || 0) - (row.defaultWeight || 0)) > 1e-9;
        const defaultLabel = fmt(row.defaultWeight, kitProfile ? 0 : 2);
        return `
        <label class="weight-row">
          <span>
            ${row.label}
            <small>Default ${defaultLabel} · ${row.group}</small>
          </span>
          <input
            type="number"
            name="weight-${profile}-${row.key}"
            step="${rules.step}"
            min="${rules.min}"
            max="${rules.max}"
            inputmode="${rules.integer ? "numeric" : "decimal"}"
            class="${isChanged ? "changed-weight-input" : ""}"
            data-weight-key="${row.key}"
            placeholder="${defaultLabel}"
            value="${row.override !== undefined ? row.override : el.weightModeSelect.value === "custom" ? row.defaultWeight : ""}"
            ${el.weightModeSelect.value === "custom" ? "" : "disabled"}
          >
        </label>
      `;
      }).join("")}
    </div>
  `;
}

function renderCompare() {
  const names = [el.compareA.value.trim(), el.compareB.value.trim()];
  const selected = names.map((name) => state.rows.find((row) => row.record.name.toLowerCase() === name.toLowerCase()));
  if (!selected[0] && !selected[1]) {
    el.compareOutput.innerHTML = "";
    return;
  }
  el.compareOutput.innerHTML = selected.map((row) => {
    if (!row) return `<div class="compare-card"><h3>No building selected</h3></div>`;
    const weightedRows = attributeRowsFor(row).filter((item) => Math.abs(item.weight) > 1e-9);
    const strengths = weightedRows.length ? weightedRows.map((item) => `
      <div class="contribution-row">
        <span>
          ${escapeHtml(displayAttributeLabel(item.label, item.key))}
          <small>Raw ${formatAttributeValue(item.key, item.raw)}${Math.abs(item.raw - item.effective) > 1e-9 ? ` · Effective ${formatAttributeValue(item.key, item.effective)}` : ""}</small>
        </span>
        <strong>${fmt(item.scorePoints)}</strong>
      </div>
    `).join("") : `<p class="empty-compare-note">No non-zero weight attributes for this profile.</p>`;
    return `
      <div class="compare-card">
        <h3>${escapeHtml(row.record.name)}</h3>
        <dl class="metric-list">
          <div><dt>Rank</dt><dd>${row.rank}</dd></div>
          <div><dt>Score</dt><dd>${fmt(row.score)}</dd></div>
          <div><dt>Efficiency</dt><dd>${fmt(row.efficiency, 3)}</dd></div>
          <div><dt>Area</dt><dd>${row.record.adjustedArea || ""}</dd></div>
        </dl>
        <div class="contributions">${strengths}</div>
      </div>
    `;
  }).join("");
}

function explainRanking(row) {
  const config = PROFILE_CONFIG[state.profile];
  const top = row.contributions.filter((item) => item.scorePoints > 0).slice(0, 3);
  const strengths = plainStrengths(top).join(", ");
  const rankText = `#${row.rank} in ${config.title}`;
  const areaText = row.record.adjustedArea
    ? `Its adjusted area is ${fmt(row.record.adjustedArea, 0)} tiles${row.record.requiresRoad ? ", including one tile for the road" : ""}.`
    : "Its building area is not available.";
  const hasCompactFootprint = Number(row.record.adjustedArea || 0) > 0 && row.record.adjustedArea < 18;
  if (!top.length) {
    return `${row.record.name} ranks ${rankText}. Its profile score is ${fmt(row.score)}, but none of its recorded benefits receives much value in this profile. ${areaText}`;
  }
  if (config.efficiency) {
    const efficiencyReason = hasCompactFootprint
      ? `Its compact footprint helps it reach ${fmt(row.efficiency, 3)} score per tile.`
      : `Together, those benefits give it ${fmt(row.efficiency, 3)} score per tile.`;
    return `${row.record.name} ranks ${rankText}. Its main strengths are ${strengths}. ${efficiencyReason} ${areaText}`;
  }
  return `${row.record.name} ranks ${rankText}. Its main strengths are ${strengths}, giving it a profile score of ${fmt(row.score)}. Building size does not affect this ranking. ${areaText}`;
}

function plainStrengthForLabel(label, key = "") {
  const kitFamily = kitFamilyForAttr(key);
  if (kitFamily) return `${kitFamily.strength.toLowerCase()} production`;
  if (label.includes("QI Action Points")) return "QI action points";
  if (label.includes("QI Coins") || label.includes("QI Goods") || label.includes("QI Units")) return "QI starting resources";
  if (label.includes("QI")) return "QI combat value";
  if (label.includes("Battleground")) return "Guild Battleground combat value";
  if (label.includes("Guild Expedition")) return "Guild Expedition combat value";
  if (label.includes("Att Boost") || label.includes("Def Boost")) return "combat boosts";
  if (label.includes("Current Age Unit")) return "current-age unit production";
  if (label.includes("Next Age Unit")) return "next-age unit production";
  if (label.includes("Rogue") || label.includes("Unit")) return "unit production";
  if (label.includes("FP") || label.includes("Strategy Points")) return "forge point output";
  if (label.includes("Guild Goods")) return "guild goods output";
  if (label.includes("Goods")) return "goods output";
  if (label.includes("Medal")) return "medal output";
  if (label.includes("Diamond") || label.includes("Premium")) return "diamond rewards";
  if (label.includes("Blueprint")) return "blueprint rewards";
  if (label.includes("Supplies")) return "supply output";
  if (label.includes("Happiness") || label.includes("Population")) return "city support";
  if (label.includes("Road")) return "road flexibility";
  return label.replace(/^Boost: /, "").replace(/^Production: /, "").toLowerCase();
}

function plainStrengths(contributions) {
  const labels = [];
  for (const item of contributions) {
    const label = plainStrengthForLabel(item.label, item.key);
    if (!labels.includes(label)) labels.push(label);
    if (labels.length >= 3) break;
  }
  return labels.length ? labels : ["its recorded production"];
}

function displayAttributeLabel(label, key = "") {
  if (key === "happiness") return "Gross Happiness";
  if (key === "happiness_demanded") return "Happiness demand";
  if (key === "prod_resource_goods_total") return "Goods Total (Calculated)";
  return label
    .replace(/^Boost: /, "")
    .replace(/^Production: /, "")
    .replace(/Att Boost/g, "Attack")
    .replace(/Def Boost/g, "Defense")
    .replace(/All$/, "All modes")
    .replace(/Strategy Points/g, "Forge Points");
}

function isPercentageAttribute(key) {
  const info = attrInfo(key);
  const description = info.description || "";
  const label = info.label || "";
  return /^Percentage\b/i.test(description) || /percentage|chance/i.test(label) || /chance/i.test(key);
}

function sortAttributeRows(rows) {
  const sorted = [...rows];
  if (state.detailSort.key === "attribute") {
    sorted.sort((a, b) => {
      const comparison = displayAttributeLabel(a.label, a.key).localeCompare(displayAttributeLabel(b.label, b.key));
      return state.detailSort.dir === "asc" ? comparison : -comparison;
    });
  } else {
    sorted.sort((a, b) => {
      const scoreComparison = a.scorePoints - b.scorePoints;
      if (Math.abs(scoreComparison) > 1e-12) {
        return state.detailSort.dir === "asc" ? scoreComparison : -scoreComparison;
      }
      return displayAttributeLabel(a.label, a.key).localeCompare(displayAttributeLabel(b.label, b.key));
    });
  }
  return sorted;
}

function orderAttributeRows(rows) {
  const happinessKeys = ["net_happiness", "happiness", "happiness_demanded"];
  const happinessRows = happinessKeys
    .map((key) => rows.find((item) => item.key === key))
    .filter(Boolean);
  if (!happinessRows.length) return rows;

  const groupedKeys = new Set(happinessRows.map((item) => item.key));
  const remainingRows = rows.filter((item) => !groupedKeys.has(item.key));
  const netHappinessIndex = rows.findIndex((item) => item.key === "net_happiness");
  const insertAt = netHappinessIndex >= 0
    ? rows.slice(0, netHappinessIndex).filter((item) => !groupedKeys.has(item.key)).length
    : remainingRows.length;
  return [
    ...remainingRows.slice(0, insertAt),
    ...happinessRows,
    ...remainingRows.slice(insertAt),
  ];
}

function attributeRowsFor(row) {
  const contributionByKey = Object.fromEntries(row.contributions.map((item) => [item.key, item]));
  const c = controls();
  const weights = customizedWeightMap(PROFILE_CONFIG[state.profile].weightProfile, c);
  const rows = Object.keys(row.record.attrs)
    .map((key) => {
      const contribution = contributionByKey[key];
      return {
        key,
        label: attrLabel(key),
        raw: rawAttr(row.record, key),
        effective: effectiveAttrValue(row.record, key, c),
        weight: weights[key] || 0,
        scorePoints: contribution?.scorePoints || 0,
      };
    })
    .filter((item) => Math.abs(item.raw) > 1e-12 || Math.abs(item.effective) > 1e-12);
  return orderAttributeRows(sortAttributeRows(rows));
}

function detailText(value) {
  const text = String(value || "").trim();
  return text ? escapeHtml(text) : `<span class="muted-text">None recorded</span>`;
}

function formatAttributeValue(key, value) {
  const formatted = fmtCompact(value);
  const kitFamily = kitFamilyForAttr(key);
  if (kitFamily) return `${formatted} ${kitFamily.unit}`;
  return formatted && isPercentageAttribute(key) ? `${formatted}%` : formatted;
}

function rawEffectiveValue(item) {
  const raw = formatAttributeValue(item.key, item.raw);
  if (Math.abs(item.raw - item.effective) <= 1e-9) return raw;
  return `${raw} (${formatAttributeValue(item.key, item.effective)})`;
}

function detailSortMarker(key) {
  if (state.detailSort.key !== key) return " ↕";
  return state.detailSort.dir === "asc" ? " ↑" : " ↓";
}

function detailAriaSort(key) {
  if (state.detailSort.key !== key) return "none";
  return state.detailSort.dir === "asc" ? "ascending" : "descending";
}

function splitCamelCase(value) {
  return String(value || "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2");
}

function humanizeToken(value) {
  const spaced = splitCamelCase(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b(\D+?)(\d+)\b/g, "$1 $2")
    .replace(/\s+/g, " ")
    .trim();
  return spaced.replace(/\b\w/g, (char) => char.toUpperCase());
}

function pluralize(noun, count) {
  if (Number(count) !== 1 && noun === "deer") return noun;
  return Number(count) === 1 ? noun : `${noun}s`;
}

function singularPhrase(label) {
  if (!label || /^[A-Z]/.test(label)) return label;
  const article = /^[aeiou]/i.test(label) ? "an" : "a";
  return `${article} ${label}`;
}

function flyingObjectPhrase(label, count) {
  return count === 1 ? `a flying ${label}` : `${count} flying ${pluralize(label, count)}`;
}

const ENVIRONMENT_SOUND_LABELS = {
  choo_choo_mf: "train whistle",
  City_Building_FountainOfYouth: "Fountain of Youth",
  City_Building_Maharajas_Temple: "Maharaja's Temple",
  City_Building_RoyalBathhouse: "Royal Bathhouse",
  City_Building_ShintoTemple: "Shinto Temple",
  City_Building_SunTemple: "Sun Temple",
  city_building_victorytower: "Victory Tower",
  City_Building_WildBonus21gBear: "bear",
  City_Building_WildBonus21gEagle: "eagle",
  City_Building_WildBonus21gMoose: "moose",
  City_Decorations_Water: "water",
  City_Building_HalloweenBonus17: "Halloween tower",
  city_building_asylumscream: "asylum scream",
  city_building_dragon_swoop: "dragon swoop",
};

const ENVIRONMENT_OBJECT_LABELS = {
  bat1: "bat",
  halloween_balloon1: "Halloween balloon",
  halloween_balloon2: "Halloween balloon",
  halloween_balloon3: "Halloween balloon",
  halloween_balloon4: "Halloween balloon",
  halloween_balloon5: "Halloween balloon",
  morgan_le_fay_dragon: "Morgan le Fay dragon",
  morgan_le_fay_dragon_shadow: "Morgan le Fay dragon shadow",
};

const ENVIRONMENT_INHABITANT_LABELS = {
  arthur: "Arthur",
  hero_knight: "hero knight",
  merlin: "Merlin",
  wildlife_deer: "deer",
  winter_doggo: "winter dog",
  soccer_chariot_a: "chariot rider",
};

function triggerText(value) {
  if (value === "on_collect") return "When collected";
  if (value === "is_built_and_connected") return "When built and connected";
  return humanizeToken(value) || "When triggered";
}

function parseEnvironmentAction(action) {
  const text = action.trim();
  let match = text.match(/^play_sound\s+(.+?)(?:\s+x(\d+))?$/i);
  if (match) {
    const label = ENVIRONMENT_SOUND_LABELS[match[1]] || humanizeToken(match[1]);
    return { type: "sound", label };
  }
  match = text.match(/^spawn_flying_object\s+(.+?)(?:\s+x(\d+))?$/i);
  if (match) {
    const count = Number(match[2] || 1);
    const label = ENVIRONMENT_OBJECT_LABELS[match[1]] || humanizeToken(match[1]).toLowerCase();
    return { type: "flyingObject", label, count };
  }
  match = text.match(/^add_unique_inhabitant\s+(.+?)(?:\s+x(\d+))?$/i);
  if (match) {
    const count = Number(match[2] || 1);
    const label = ENVIRONMENT_INHABITANT_LABELS[match[1]] || humanizeToken(match[1]);
    return { type: "inhabitant", label, count };
  }
  match = text.match(/^spawn_chain_building_inhabitants\s+(.+?)(?:\s+x(\d+))?$/i);
  if (match) {
    const count = Number(match[2] || 1);
    const label = ENVIRONMENT_INHABITANT_LABELS[match[1]] || humanizeToken(match[1]).toLowerCase();
    return { type: "chainInhabitant", label, count };
  }
  return { type: "text", text: humanizeToken(text).toLowerCase() };
}

function environmentActionText(action) {
  if (action.type === "sound") return `plays the ${action.label} sound`;
  if (action.type === "flyingObject") return `shows ${flyingObjectPhrase(action.label, action.count)}`;
  if (action.type === "inhabitant") {
    return action.count === 1
      ? `adds ${singularPhrase(action.label)} as a visible city character`
      : `adds ${action.count} ${pluralize(action.label, action.count)} as visible city characters`;
  }
  if (action.type === "chainInhabitant") {
    return action.count === 1
      ? `adds a chain-building ${action.label}`
      : `adds ${action.count} chain-building ${pluralize(action.label, action.count)}`;
  }
  return action.text;
}

function mergeEnvironmentActions(actions) {
  const merged = new Map();
  actions.forEach((action) => {
    const key = action.type === "text" ? `${action.type}:${action.text}` : `${action.type}:${action.label}`;
    if (!merged.has(key)) {
      merged.set(key, { ...action });
    } else if (Number.isFinite(action.count)) {
      merged.get(key).count += action.count;
    }
  });
  return [...merged.values()];
}

function describeEnvironmentAction(action) {
  return environmentActionText(parseEnvironmentAction(action));
}

function describeEnvironmentEffect(value) {
  const text = String(value || "").trim();
  if (!text) return "";
  const grouped = new Map();
  text.split(";")
    .map((part) => part.trim())
    .filter(Boolean)
    .forEach((part) => {
      const [trigger, action] = part.split(/\s+-\s+/, 2);
      const key = triggerText(trigger || "");
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(parseEnvironmentAction(action || part));
    });
  return Array.from(grouped.entries()).map(([trigger, actions]) => {
    const actionText = mergeEnvironmentActions(actions).map(environmentActionText);
    return `${trigger}, ${actionText.join("; ")}.`;
  }).join(" ");
}

function buildReportText(row) {
  const attrSelect = document.getElementById("reportAttribute");
  const observed = document.getElementById("observedValue")?.value.trim();
  const notes = document.getElementById("reportNotes")?.value.trim();
  const selectedKey = attrSelect?.value || "";
  const attrRows = attributeRowsFor(row);
  const selected = attrRows.find((item) => item.key === selectedKey);
  return [
    "FOE Building Ranking discrepancy report",
    `Building: ${row.record.name}`,
    `Entity ID: ${row.record.entityId}`,
    `City age: ${DATA.ages.find((age) => age.key === controls().age)?.label || controls().age}`,
    `Profile: ${PROFILE_CONFIG[state.profile].title}`,
    `Rank: ${row.rank}`,
    `Score: ${fmt(row.score)}`,
    `Efficiency: ${fmt(row.efficiency, 3)}`,
    `Attribute checked: ${selected ? displayAttributeLabel(selected.label, selected.key) : "Not selected"}`,
    `Expected value: ${selected ? formatAttributeValue(selected.key, selected.effective) : "N/A"}`,
    `Observed value: ${observed || "Not provided"}`,
    `Notes: ${notes || "None"}`,
  ].join("\n");
}

function kitItemProductionText(item) {
  const expectedKits = fmtCompact(Number(item.kitEquivalentsPerDay || 0));
  const possibleKits = fmtCompact(Number(item.possibleKitEquivalentsPerDay || 0));
  const expectedFragments = fmtCompact(Number(item.expectedFragmentsPerDay || 0));
  const possibleFragments = fmtCompact(Number(item.possibleFragmentsPerDay || 0));
  const chance = Number(item.chance ?? 1);
  const durationText = item.durationHours ? ` Each completed reward provides a ${fmtCompact(item.durationHours)}-hour supply rush.` : "";
  if (item.source === "kit") {
    const possibleText = chance < 0.999
      ? ` Possible output is ${possibleKits} kits/day at ${(chance * 100).toLocaleString(undefined, { maximumFractionDigits: 1 })}%.`
      : "";
    return `${expectedKits} expected completed kits/day.${possibleText}${durationText}`;
  }
  const possibleText = chance < 0.999
    ? ` The possible output is ${possibleFragments} fragments/day, or ${possibleKits} kits/day.`
    : "";
  return `${expectedFragments} expected fragments/day, with ${fmtCompact(item.requiredFragments)} needed per kit. That equals ${expectedKits} kits/day.${possibleText}${durationText}`;
}

function renderKitProductionDetails(record) {
  const production = kitProductionForRecord(record);
  const families = KIT_FAMILIES.filter((family) => production[family.key]);
  if (!families.length) return "";
  return `
    <h3>Kit Production</h3>
    <p class="detail-section-note">Expected values include collection frequency and reward probability. Each family shows the building's best available production option, so different families may come from different choices.</p>
    <div class="kit-detail-grid">
      ${families.map((family) => {
        const familyProduction = production[family.key];
        const primaryValue = family.key === "supplyFinish"
          ? `${fmtCompact(familyProduction.valuePerDay)} rush hours/day`
          : `${fmtCompact(familyProduction.kitEquivalentsPerDay)} kits/day`;
        return `
          <article class="kit-detail-card">
            <div class="kit-detail-heading">
              <span class="badge kit">${escapeHtml(family.strength)}</span>
              <strong>${escapeHtml(primaryValue)}</strong>
            </div>
            <div class="kit-detail-items">
              ${familyProduction.items.map((item) => `
                <div>
                  <strong>${escapeHtml(item.label)}</strong>
                  <p>${escapeHtml(kitItemProductionText(item))}</p>
                </div>
              `).join("")}
            </div>
          </article>
        `;
      }).join("")}
    </div>
  `;
}

function setBackgroundInert(inert) {
  [document.querySelector(".app-header"), document.querySelector(".layout")].forEach((region) => {
    if (region) region.inert = inert;
  });
}

function drawerFocusableElements() {
  return Array.from(el.detailDrawer.querySelectorAll(
    'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])'
  )).filter((item) => item.getClientRects().length > 0);
}

function trapDetailFocus(event) {
  if (event.key !== "Tab" || !el.detailDrawer.classList.contains("open")) return;
  const focusable = drawerFocusableElements();
  if (!focusable.length) {
    event.preventDefault();
    el.detailDrawer.focus();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const active = document.activeElement;
  if (event.shiftKey && (active === first || !el.detailDrawer.contains(active))) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || !el.detailDrawer.contains(active))) {
    event.preventDefault();
    first.focus();
  }
}

function openDetail(entityId, focusClose = true, returnFocus = null) {
  const row = state.rows.find((item) => item.record.entityId === entityId);
  if (!row) return;
  if (focusClose) {
    state.detailReturnFocus = returnFocus
      || (!el.detailDrawer.contains(document.activeElement) ? document.activeElement : state.detailReturnFocus);
  }
  if (state.activeDetailEntityId !== entityId) state.detailSelectedAttributeKey = null;
  state.activeDetailEntityId = entityId;
  const attrRows = attributeRowsFor(row);
  if (!attrRows.some((item) => item.key === state.detailSelectedAttributeKey)) {
    state.detailSelectedAttributeKey = attrRows[0]?.key || "";
  }
  const detailRows = [
    ["Environment effect", describeEnvironmentEffect(row.record.environmentEffect)],
    ["Reward production", row.record.rewardProduction],
  ].map(([label, value]) => `
    <div class="detail-info-row">
      <span>${escapeHtml(label)}</span>
      <strong>${detailText(value)}</strong>
    </div>
  `).join("");
  const attrOptions = attrRows.slice(0, 80).map((item) => `
    <option value="${escapeHtml(item.key)}"${item.key === state.detailSelectedAttributeKey ? " selected" : ""}>${escapeHtml(displayAttributeLabel(item.label, item.key))}</option>
  `).join("");
  const attrTableRows = attrRows.map((item) => `
    <tr class="attribute-row${item.key === state.detailSelectedAttributeKey ? " selected-attribute-row" : ""}" data-attribute-key="${escapeHtml(item.key)}" tabindex="0">
      <td>${escapeHtml(displayAttributeLabel(item.label, item.key))}</td>
      <td>${rawEffectiveValue(item)}</td>
      <td>${fmt(item.scorePoints)}</td>
      <td>${fmt(item.weight)}</td>
      <td>${Math.abs(item.weight) > 1e-9 ? "Used" : "Not used"}</td>
    </tr>
  `).join("");
  el.detailContent.innerHTML = `
    <h2 class="detail-title" id="detailTitle">${escapeHtml(row.record.name)}</h2>
    <p class="detail-subtitle">${escapeHtml(row.record.category)}</p>
    <div class="detail-grid">
      <div class="detail-stat"><span>Rank</span><strong>${row.rank}</strong></div>
      <div class="detail-stat"><span>Score</span><strong>${fmt(row.score)}</strong></div>
      <div class="detail-stat"><span>Efficiency</span><strong>${fmt(row.efficiency, 3)}</strong></div>
      <div class="detail-stat"><span>Size</span><strong>${row.record.size || "Unknown"}</strong></div>
      <div class="detail-stat"><span>Adjusted area</span><strong>${row.record.adjustedArea || ""}</strong></div>
      <div class="detail-stat"><span>Road connection</span><strong>${row.record.requiresRoad ? "Required" : "No"}</strong></div>
    </div>
    <h3>Summary</h3>
    <p class="detail-summary">${escapeHtml(explainRanking(row))}</p>
    ${renderKitProductionDetails(row.record)}
    <h3>Ranking Attributes</h3>
    <div class="attribute-table-wrap">
      <table class="attribute-table signal-table">
        <thead>
          <tr>
            <th aria-sort="${detailAriaSort("attribute")}">
              <button class="detail-sort-button" type="button" data-detail-sort="attribute">Attribute${detailSortMarker("attribute")}</button>
            </th>
            <th>Raw (Effective) value</th>
            <th aria-sort="${detailAriaSort("score")}">
              <button class="detail-sort-button" type="button" data-detail-sort="score">Ranking score${detailSortMarker("score")}</button>
            </th>
            <th>Weight</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${attrTableRows}</tbody>
      </table>
    </div>
    <h3>Additional Building Details</h3>
    <div class="detail-info-list">${detailRows}</div>
    <h3>Report Discrepancy</h3>
    <div class="report-box">
      <label>Attribute <select id="reportAttribute">${attrOptions}</select></label>
      <label>Observed in game <input id="observedValue" type="text" placeholder="Value you see"></label>
      <label>Notes <textarea id="reportNotes" rows="3" placeholder="What looks wrong?"></textarea></label>
      <button id="copyReportButton" type="button" class="secondary-button">Copy report</button>
      <textarea id="reportOutput" rows="8" readonly placeholder="Copied report text will appear here. Please send it to me as an in-game PM. Thanks! 😊 -- zpwd"></textarea>
    </div>
  `;
  el.detailDrawer.classList.add("open");
  el.detailDrawer.setAttribute("aria-hidden", "false");
  el.drawerBackdrop.hidden = false;
  document.body.classList.add("drawer-open");
  setBackgroundInert(true);
  el.detailContent.querySelectorAll("[data-detail-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.detailSort;
      if (state.detailSort.key === key) {
        state.detailSort.dir = state.detailSort.dir === "asc" ? "desc" : "asc";
      } else {
        state.detailSort = { key, dir: key === "attribute" ? "asc" : "desc" };
      }
      openDetail(entityId, false);
      el.detailContent.querySelector(`[data-detail-sort="${key}"]`)?.focus();
    });
  });
  if (focusClose) el.closeDrawer.focus();
}

function closeDetail() {
  if (!el.detailDrawer.classList.contains("open")) return;
  const returnFocus = state.detailReturnFocus;
  if (el.detailDrawer.contains(document.activeElement)) document.activeElement.blur();
  el.detailDrawer.classList.remove("open");
  el.detailDrawer.setAttribute("aria-hidden", "true");
  el.drawerBackdrop.hidden = true;
  document.body.classList.remove("drawer-open");
  setBackgroundInert(false);
  state.activeDetailEntityId = null;
  state.detailSelectedAttributeKey = null;
  state.detailReturnFocus = null;
  if (returnFocus?.isConnected) {
    requestAnimationFrame(() => returnFocus.focus());
  }
}

function render() {
  const rows = buildRows();
  const visibleRows = filteredRows(rows);
  renderControlState(rows, visibleRows);
  renderSummary(rows);
  renderTable(rows);
  renderBuildingList();
  renderCustomWeights();
  renderCompare();
  updateUrl();
}

function renderImmediately() {
  window.clearTimeout(renderTimer);
  renderTimer = null;
  pendingAfterRender = null;
  render();
}

function scheduleRender(delay = 100, afterRender = null) {
  window.clearTimeout(renderTimer);
  pendingAfterRender = afterRender;
  renderTimer = window.setTimeout(() => {
    renderTimer = null;
    const callback = pendingAfterRender;
    pendingAfterRender = null;
    render();
    callback?.();
  }, delay);
}

function resetDefaults() {
  const defaults = DATA.defaults;
  el.presetSelect.value = "";
  el.ageSelect.value = DATA.metadata.defaultAge;
  el.categorySelect.value = ALL_CATEGORIES;
  el.searchInput.value = "";
  el.qiRoleSelect.value = defaults.qiFighterRole;
  el.gbgGeFocus.value = defaults.fightingGbgGeFocus;
  el.redBlueFocus.value = defaults.fightingRedBlueFocus;
  el.attackDefenseFocus.value = defaults.fightingAttackDefenseFocus;
  el.unitAgeFocus.value = defaults.fightingUnitAgeFocus;
  el.fpGoodsFocus.value = defaults.productionFpGoodsFocus;
  el.fpEstimate.value = defaults.estimatedFpProduction;
  el.goodsEstimate.value = defaults.estimatedGoodsProduction;
  el.guildGoodsEstimate.value = defaults.estimatedGuildGoodsProduction;
  el.medalEstimate.value = defaults.estimatedMedalProduction;
  el.specialGoodsEstimate.value = defaults.estimatedSpecialGoodsProduction;
  el.strengthFilter.value = "";
  el.minAreaFilter.value = "";
  el.maxAreaFilter.value = "";
  el.noRoadFilter.checked = false;
  el.topNSelect.value = "200";
  el.weightModeSelect.value = "default";
  state.customWeights = {
    overall: {},
    fighting: {},
    farming: {},
    qi: {},
    kits: {},
  };
  state.sort = { key: "profile", dir: "desc" };
}

function setActiveProfile(profile) {
  if (!PROFILE_CONFIG[profile]) return;
  state.profile = profile;
  syncProfileTabs();
}

function syncProfileTabs() {
  let activeTab = null;
  document.querySelectorAll(".tab").forEach((tab) => {
    const selected = tab.dataset.profile === state.profile;
    tab.classList.toggle("active", selected);
    tab.setAttribute("aria-selected", selected ? "true" : "false");
    tab.tabIndex = selected ? 0 : -1;
    if (selected) activeTab = tab;
  });
  if (activeTab) {
    document.getElementById("rankingPanel")?.setAttribute("aria-labelledby", activeTab.id);
  }
}

function applyPreset(presetKey) {
  const preset = PRESETS[presetKey];
  if (!preset) return;
  setActiveProfile(preset.profile);
  const values = preset.values;
  el.qiRoleSelect.value = values.qiRole;
  el.gbgGeFocus.value = values.gbgGeFocus;
  el.redBlueFocus.value = values.redBlueFocus;
  el.attackDefenseFocus.value = values.attackDefenseFocus;
  el.unitAgeFocus.value = values.unitAgeFocus;
  el.fpGoodsFocus.value = values.fpGoodsFocus;
  el.weightModeSelect.value = "default";
}

function encodeState(value) {
  const json = JSON.stringify(value);
  const bytes = new TextEncoder().encode(json);
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function decodeState(value) {
  try {
    const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
    const padded = normalized + "=".repeat((4 - normalized.length % 4) % 4);
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch (_error) {
    return null;
  }
}

function buildUrlParams() {
  const c = controls();
  const params = new URLSearchParams();
  params.set("profile", state.profile);
  if (PRESET_PROFILES_ENABLED && el.presetSelect.value) params.set("preset", el.presetSelect.value);
  params.set("age", c.age);
  if (c.category !== ALL_CATEGORIES) params.set("category", c.category);
  if (c.search) params.set("search", c.search);
  params.set("role", c.qiRole);
  params.set("gbgGe", c.gbgGeFocus);
  params.set("redBlue", c.redBlueFocus);
  params.set("attackDefense", c.attackDefenseFocus);
  params.set("unitAge", c.unitAgeFocus);
  params.set("fpGoods", c.fpGoodsFocus);
  params.set("fp", c.estimatedFpProduction);
  params.set("goods", c.estimatedGoodsProduction);
  params.set("guildGoods", c.estimatedGuildGoodsProduction);
  params.set("medals", c.estimatedMedalProduction);
  params.set("specialGoods", c.estimatedSpecialGoodsProduction);
  if (c.strength) params.set("strength", c.strength);
  if (c.minArea !== null) params.set("minArea", c.minArea);
  if (c.maxArea !== null) params.set("maxArea", c.maxArea);
  if (c.noRoadOnly) params.set("noRoad", "1");
  if (c.topN !== "200") params.set("topN", c.topN);
  if (el.weightModeSelect.value === "custom") params.set("mode", "custom");
  if (state.sort.key !== "profile" || state.sort.dir !== "desc") {
    params.set("sort", `${state.sort.key}:${state.sort.dir}`);
  }
  const hasOverrides = Object.values(state.customWeights).some((profile) => Object.keys(profile).length > 0);
  if (hasOverrides) params.set("weights", encodeState(state.customWeights));
  return params;
}

function updateUrl() {
  if (state.suppressUrlUpdate) return;
  const params = buildUrlParams();
  const nextUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.replaceState(null, "", nextUrl);
}

function applyUrlState() {
  const params = new URLSearchParams(window.location.search);
  if (!params.size) return;
  state.suppressUrlUpdate = true;
  if (PRESET_PROFILES_ENABLED && params.get("preset") && PRESETS[params.get("preset")]) {
    el.presetSelect.value = params.get("preset");
    applyPreset(params.get("preset"));
  }
  setActiveProfile(params.get("profile") || state.profile);
  if (params.get("age")) el.ageSelect.value = params.get("age");
  if (params.get("category")) el.categorySelect.value = params.get("category");
  if (params.get("search")) el.searchInput.value = params.get("search");
  if (params.get("role")) el.qiRoleSelect.value = params.get("role");
  if (params.get("gbgGe")) el.gbgGeFocus.value = params.get("gbgGe");
  if (params.get("redBlue")) el.redBlueFocus.value = params.get("redBlue");
  if (params.get("attackDefense")) el.attackDefenseFocus.value = params.get("attackDefense");
  if (params.get("unitAge")) el.unitAgeFocus.value = params.get("unitAge");
  if (params.get("fpGoods")) el.fpGoodsFocus.value = params.get("fpGoods");
  if (params.get("fp")) el.fpEstimate.value = params.get("fp");
  if (params.get("goods")) el.goodsEstimate.value = params.get("goods");
  if (params.get("guildGoods")) el.guildGoodsEstimate.value = params.get("guildGoods");
  if (params.get("medals")) el.medalEstimate.value = params.get("medals");
  if (params.get("specialGoods")) el.specialGoodsEstimate.value = params.get("specialGoods");
  if (params.get("strength")) el.strengthFilter.value = params.get("strength");
  if (params.get("minArea")) el.minAreaFilter.value = params.get("minArea");
  if (params.get("maxArea")) el.maxAreaFilter.value = params.get("maxArea");
  el.noRoadFilter.checked = params.get("noRoad") === "1";
  if (params.get("topN")) el.topNSelect.value = params.get("topN");
  if (params.get("mode") === "custom") el.weightModeSelect.value = "custom";
  if (params.get("sort")) {
    const [key, dir] = params.get("sort").split(":");
    if (key && dir) state.sort = { key, dir };
  }
  const decodedWeights = params.get("weights") ? decodeState(params.get("weights")) : null;
  if (decodedWeights && typeof decodedWeights === "object") {
    state.customWeights = sanitizeCustomWeightState(decodedWeights);
  }
  state.suppressUrlUpdate = false;
}

function initMobileCollapsibles() {
  const mobileQuery = window.matchMedia("(max-width: 1100px)");
  const mobileSettings = document.querySelector("[data-mobile-settings]");
  const sync = () => {
    if (mobileSettings) mobileSettings.open = !mobileQuery.matches;
    document.querySelectorAll("[data-mobile-collapsible]").forEach((section) => {
      section.open = !mobileQuery.matches;
    });
  };
  sync();
  mobileQuery.addEventListener("change", sync);
}

function init() {
  el.versionLabel.textContent = `Model ${DATA.metadata.workbookModelVersion} · Last updated ${DATA.metadata.generatedAt}`;
  el.ageSelect.innerHTML = DATA.ages.map((age) => `<option value="${escapeHtml(age.key)}" title="${escapeHtml(age.label)}">${escapeHtml(age.label)}</option>`).join("");
  el.categorySelect.innerHTML = DATA.categories.map((category) => `<option value="${escapeHtml(category)}" title="${escapeHtml(category)}">${escapeHtml(category)}</option>`).join("");
  resetDefaults();
  applyUrlState();
  initMobileCollapsibles();
  renderStrengthLegend();

  document.addEventListener("click", (event) => {
    const button = event.target.closest(".info-button");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    const target = document.getElementById(button.getAttribute("aria-controls"));
    if (!target) return;
    const expanded = button.getAttribute("aria-expanded") !== "true";
    button.setAttribute("aria-expanded", expanded ? "true" : "false");
    target.hidden = !expanded;
    const label = button.dataset.infoLabel || "section";
    button.setAttribute("aria-label", `${expanded ? "Hide" : "Show"} ${label} information`);
  });

  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      el.presetSelect.value = "";
      setActiveProfile(button.dataset.profile);
      state.sort = { key: "profile", dir: "desc" };
      renderImmediately();
    });
  });

  document.querySelector(".tabs").addEventListener("keydown", (event) => {
    const current = event.target.closest('[role="tab"]');
    if (!current) return;
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    const currentIndex = tabs.indexOf(current);
    let nextIndex = null;
    if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabs.length;
    if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") nextIndex = 0;
    if (event.key === "End") nextIndex = tabs.length - 1;
    if (nextIndex === null) return;
    event.preventDefault();
    tabs[nextIndex].focus();
    tabs[nextIndex].click();
  });

  [
    el.ageSelect,
    el.categorySelect,
    el.qiRoleSelect,
    el.strengthFilter,
    el.noRoadFilter,
    el.topNSelect,
    el.weightModeSelect,
  ].forEach((input) => input.addEventListener("change", renderImmediately));

  el.searchInput.addEventListener("input", () => scheduleRender(160));

  [
    el.gbgGeFocus,
    el.redBlueFocus,
    el.attackDefenseFocus,
    el.unitAgeFocus,
    el.fpGoodsFocus,
  ].forEach((input) => input.addEventListener("input", () => {
    syncFocusOutputs();
    scheduleRender(80);
  }));

  [
    el.fpEstimate,
    el.goodsEstimate,
    el.guildGoodsEstimate,
    el.medalEstimate,
    el.specialGoodsEstimate,
    el.minAreaFilter,
    el.maxAreaFilter,
  ].forEach((input) => input.addEventListener("input", () => scheduleRender(120)));

  el.presetSelect.addEventListener("change", () => {
    applyPreset(el.presetSelect.value);
    renderImmediately();
  });

  document.querySelectorAll(".sort-button").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.sort;
      if (state.sort.key === key) {
        state.sort.dir = state.sort.dir === "asc" ? "desc" : "asc";
      } else {
        state.sort = { key, dir: key === "name" || key === "area" ? "asc" : "desc" };
      }
      renderImmediately();
    });
  });

  el.resetButton.addEventListener("click", () => {
    resetDefaults();
    renderImmediately();
    announce("Dashboard defaults restored.");
  });
  el.shareButton.addEventListener("click", async () => {
    updateUrl();
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      el.shareButton.textContent = "Copied";
      announce("Share link copied.");
      setTimeout(() => { el.shareButton.textContent = "Copy share link"; }, 1200);
    } catch (_error) {
      window.prompt("Copy this link", url);
    }
  });
  el.resetWeightsButton.addEventListener("click", () => {
    state.customWeights[activeWeightProfile()] = {};
    renderImmediately();
    announce("Weights for the active profile restored.");
  });
  el.customWeights.addEventListener("input", (event) => {
    const input = event.target.closest("input[data-weight-key]");
    if (!input) return;
    const weightList = el.customWeights.querySelector(".weight-list");
    const previousScrollTop = weightList?.scrollTop || 0;
    const profile = activeWeightProfile();
    const key = input.dataset.weightKey;
    const value = input.value.trim();
    if (!state.customWeights[profile]) state.customWeights[profile] = {};
    if (value === "") {
      delete state.customWeights[profile][key];
    } else {
      const sanitized = sanitizeCustomWeight(profile, value);
      state.customWeights[profile][key] = sanitized;
      input.value = String(sanitized);
    }
    scheduleRender(140, () => {
      const nextWeightList = el.customWeights.querySelector(".weight-list");
      if (nextWeightList) nextWeightList.scrollTop = previousScrollTop;
      const nextInput = Array.from(el.customWeights.querySelectorAll("input[data-weight-key]"))
        .find((candidate) => candidate.dataset.weightKey === key);
      if (nextInput && document.activeElement === document.body) {
        try {
          nextInput.focus({ preventScroll: true });
        } catch (_error) {
          nextInput.focus();
        }
      }
    });
  });
  el.closeDrawer.addEventListener("click", closeDetail);
  el.drawerBackdrop.addEventListener("click", closeDetail);
  el.rankingBody.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-entity-id]");
    if (row) {
      const returnFocus = event.target.closest(".details-button") || row.querySelector(".details-button");
      openDetail(row.dataset.entityId, true, returnFocus);
    }
  });
  el.detailContent.addEventListener("click", async (event) => {
    const attrRow = event.target.closest("tr[data-attribute-key]");
    if (attrRow) {
      const attrSelect = document.getElementById("reportAttribute");
      state.detailSelectedAttributeKey = attrRow.dataset.attributeKey;
      if (attrSelect) {
        attrSelect.value = state.detailSelectedAttributeKey;
        el.detailContent.querySelectorAll("tr[data-attribute-key]").forEach((row) => {
          row.classList.toggle("selected-attribute-row", row === attrRow);
        });
      }
      return;
    }

    const button = event.target.closest("#copyReportButton");
    if (!button) return;
    const row = state.rows.find((item) => item.record.entityId === state.activeDetailEntityId);
    if (!row) return;
    const reportText = buildReportText(row);
    const output = document.getElementById("reportOutput");
    if (output) output.value = reportText;
    try {
      await navigator.clipboard.writeText(reportText);
      button.textContent = "Copied";
      announce("Building report copied.");
      setTimeout(() => { button.textContent = "Copy report"; }, 1200);
    } catch (_error) {
      if (output) {
        output.focus();
        output.select();
      }
    }
  });
  el.detailContent.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const attrRow = event.target.closest("tr[data-attribute-key]");
    if (!attrRow) return;
    event.preventDefault();
    attrRow.click();
  });
  el.detailContent.addEventListener("change", (event) => {
    const attrSelect = event.target.closest("#reportAttribute");
    if (!attrSelect) return;
    state.detailSelectedAttributeKey = attrSelect.value;
    el.detailContent.querySelectorAll("tr[data-attribute-key]").forEach((row) => {
      row.classList.toggle("selected-attribute-row", row.dataset.attributeKey === state.detailSelectedAttributeKey);
    });
  });
  el.compareA.addEventListener("input", () => {
    syncLongValuePresentation();
    renderCompare();
  });
  el.compareB.addEventListener("input", () => {
    syncLongValuePresentation();
    renderCompare();
  });
  document.getElementById("viewRankingsButton").addEventListener("click", () => {
    const mobileSettings = document.querySelector("[data-mobile-settings]");
    if (mobileSettings) mobileSettings.open = false;
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    document.querySelector(".tabs")?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeDetail();
      return;
    }
    trapDetailFocus(event);
  });

  render();
}

init();
