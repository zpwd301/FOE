const MAX_LEVEL = 301;
const ARC_FIRST_TEN_BONUSES = [10, 12, 14, 17, 19, 22, 24, 26, 29, 31];
const BUILDING_BENEFITS = Object.freeze({
  X_AllAge_EasterBonus4: "Guild treasury goods · city-defense army boost",
  X_AllAge_Oracle: "Supplies · happiness",
  X_AllAge_Expedition: "Relics from Guild Expedition encounters",
  X_BronzeAge_Landmark2: "Offensive army boost",
  X_BronzeAge_Landmark1: "Goods · population",
  X_IronAge_Landmark1: "Medals · happiness",
  X_IronAge_Landmark2: "Goods · boosted supply production",
  X_EarlyMiddleAge_Landmark2: "Coins · offensive army boost",
  X_EarlyMiddleAge_Landmark3: "Goods · chance to repel plunder",
  X_EarlyMiddleAge_Landmark1: "Forge Points · happiness",
  X_HighMiddleAge_Landmark3: "Supplies · happiness",
  X_HighMiddleAge_Landmark1: "Goods · boosted coin production",
  X_LateMiddleAge_Landmark3: "Forge Points · offensive army boost",
  X_LateMiddleAge_Landmark1: "Coins · city-defense army boost",
  X_ColonialAge_Landmark2: "Medals · city-defense army boost",
  X_ColonialAge_Landmark1: "Goods · happiness",
  X_IndustrialAge_Landmark2: "Supplies · population",
  X_IndustrialAge_Landmark1: "Goods · boosted supply production",
  X_ProgressiveEra_Landmark1: "Unattached military units · happiness",
  X_ProgressiveEra_Landmark2: "Coins · boosted quest rewards",
  X_ModernEra_Landmark2: "Guild treasury goods · happiness",
  X_ModernEra_Landmark1: "Coins · happiness",
  X_PostModernEra_Landmark1: "Forge Points",
  X_PostModernEra_Landmark2: "Coins · population",
  X_ContemporaryEra_Landmark2: "Forge Points · population",
  X_ContemporaryEra_Landmark1: "Coins · happiness",
  X_TomorrowEra_Landmark2: "Supplies · goods when aiding",
  X_TomorrowEra_Landmark1: "Supplies · goods when plundering",
  X_FutureEra_Landmark2: "Goods · blueprint chance when aiding",
  X_FutureEra_Landmark1: "Guild treasury goods · boosted GB contribution rewards",
  X_ArcticFuture_Landmark2: "Forge Points · critical-hit chance",
  X_ArcticFuture_Landmark1: "Medals · happiness",
  X_ArcticFuture_Landmark3: "Supplies · bonus rewards when aiding",
  X_OceanicFuture_Landmark1: "Goods · chance to double plunder",
  X_OceanicFuture_Landmark3: "Medals · chance to double building collections",
  X_OceanicFuture_Landmark2: "Forge Points · chance to defeat an enemy unit before battle",
  X_VirtualFuture_Landmark2: "Supplies · rewards from won battles",
  X_VirtualFuture_Landmark1: "All-army attack and defense",
  X_SpaceAgeMars_Landmark1: "Previous-era goods",
  X_SpaceAgeMars_Landmark2: "Coins · chance to destroy half an enemy army before battle",
  X_SpaceAgeAsteroidBelt_Landmark1: "Special goods · rewards from successful negotiations",
  X_SpaceAgeVenus_Landmark1: "Mysterious Shards for Cultural Settlements",
  X_SpaceAgeJupiterMoon_Landmark1: "Special-goods production boost · guild treasury goods",
  X_SpaceAgeTitan_Landmark1: "Previous-era goods · offensive army boost",
  X_SpaceAgeTitan_Landmark3: "Guild treasury goods · all-army attack and defense",
  X_SpaceAgeTitan_Landmark2: "Forge Points · city-defense army boost",
  X_SpaceAgeSpaceHub_Landmark2: "Guild treasury goods · critical-hit chance",
  X_SpaceAgeSpaceHub_Landmark1: "Unattached military units · all-army attack and defense",
  X_StellarAgeDiscovery_Landmark1: "Supplies · all-army attack and defense",
});

const BENEFIT_DETAILS = Object.freeze({
  advanced_tactics: { label: "All-army attack & defense", unit: "%" },
  aid_boost: { label: "Blueprint chance when aiding", unit: "%" },
  aid_goods: { label: "Goods from aiding (total)", unit: "goods" },
  algorithmic_core: { label: "Special-goods production boost", unit: "%" },
  clan_goods: { label: "Guild treasury goods (total)", unit: "goods" },
  contribution_boost: { label: "GB contribution boost", unit: "%" },
  critical_hit_chance: { label: "Critical-hit chance", unit: "%" },
  diplomatic_gifts: { label: "Diplomatic Gifts chance", unit: "%" },
  double_collection: { label: "Double-collection chance", unit: "%" },
  fierce_resistance: { label: "City-defense attack & defense", unit: "%" },
  first_strike: { label: "First-strike chance", unit: "%" },
  happiness: { label: "Happiness", unit: "" },
  helping_hands: { label: "Helping Hands chance", unit: "%" },
  medals: { label: "Medals", unit: "medals" },
  military_boost: { label: "Offensive army boost", unit: "%" },
  missile_launch: { label: "Missile-launch chance", unit: "%" },
  money: { label: "Coins", unit: "coins" },
  money_boost: { label: "Coin production boost", unit: "%" },
  mysterious_shards: { label: "Mysterious Shard chance", unit: "%" },
  penal_unit: { label: "Unattached military units", unit: "units" },
  plunder_and_pillage: { label: "Plunder bonus", unit: "%" },
  plunder_goods: { label: "Goods from plundering (total)", unit: "goods" },
  plunder_repel: { label: "Plunder-repel chance", unit: "%" },
  population: { label: "Population", unit: "" },
  previous_era_goods: { label: "Previous-era goods (total)", unit: "goods" },
  quest_boost: { label: "Quest reward boost", unit: "%" },
  random_goods: { label: "Goods production (through Modern)", unit: "goods" },
  random_goods_after_modern: { label: "Goods production (Postmodern+)", unit: "goods" },
  special_goods: { label: "Special goods", unit: "goods" },
  spoils_of_war: { label: "Spoils of War chance", unit: "%" },
  strategy_points: { label: "Forge Points", unit: "FP" },
  supplies: { label: "Supplies", unit: "supplies" },
  supplies_boost: { label: "Supply production boost", unit: "%" },
  support_boost: { label: "Guild support pool", unit: "%" },
  totem_drop: { label: "Relic hunt chance", unit: "%" },
});

export function buildingBenefit(buildingId) {
  return BUILDING_BENEFITS[buildingId] ?? "Benefit details unavailable";
}

export function benefitDefinition(key) {
  if (BENEFIT_DETAILS[key]) return BENEFIT_DETAILS[key];
  return {
    label: String(key)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (character) => character.toUpperCase()),
    unit: "",
  };
}

export function benefitsForLevel(building, targetLevel) {
  assertTargetLevel(targetLevel);
  return (building.benefits ?? [])
    .map((benefit) => ({
      key: benefit.key,
      value: benefit.values?.[targetLevel - 1],
    }))
    .filter((benefit) => Number.isFinite(benefit.value));
}

export function assertTargetLevel(targetLevel, maxLevel = MAX_LEVEL) {
  if (!Number.isInteger(targetLevel) || targetLevel < 1 || targetLevel > maxLevel) {
    throw new RangeError(`Target level must be an integer from 1 to ${maxLevel}`);
  }
}

export function forgeHammerRound(value) {
  const epsilon = 0.000001;
  return Math.round(value + (value >= 0 ? epsilon : -epsilon));
}

export function arcBonusForLevel(arcLevel) {
  if (!Number.isInteger(arcLevel) || arcLevel < 0 || arcLevel > 180) {
    throw new RangeError("Arc level must be an integer from 0 to 180+");
  }
  if (arcLevel === 0) return 0;
  if (arcLevel <= 10) return ARC_FIRST_TEN_BONUSES[arcLevel - 1];
  if (arcLevel <= 58) return arcLevel + 21;
  if (arcLevel <= 80) return 79 + (arcLevel - 58) * 0.5;
  return Math.round((90 + (arcLevel - 80) * 0.1) * 10) / 10;
}

export function arcLevelForBonus(arcBonus) {
  const bonus = Number(arcBonus);
  if (!Number.isFinite(bonus)) return 0;
  let closestLevel = 0;
  let closestDifference = Math.abs(bonus);
  for (let level = 1; level <= 180; level += 1) {
    const difference = Math.abs(arcBonusForLevel(level) - bonus);
    if (difference <= closestDifference) {
      closestLevel = level;
      closestDifference = difference;
    }
  }
  return closestLevel;
}

export function upgradeCost(firstTenLevelCosts, targetLevel) {
  assertTargetLevel(targetLevel);
  if (!Array.isArray(firstTenLevelCosts) || firstTenLevelCosts.length !== 10) {
    throw new TypeError("Exactly ten seed costs are required");
  }
  if (targetLevel <= 10) {
    return firstTenLevelCosts[targetLevel - 1];
  }
  return Math.ceil(firstTenLevelCosts[9] * Math.pow(1.025, targetLevel - 10));
}

function emptyUnlockCosts() {
  return { blueprintSets: 0, goods: {}, resources: {} };
}

export function unlockCostsForLevel(building, targetLevel) {
  assertTargetLevel(targetLevel);
  const formula = building.levelUnlockFormula ?? {};
  const startLevel = formula.startLevel ?? 11;
  if (targetLevel < startLevel) return emptyUnlockCosts();

  const step = targetLevel - startLevel + 1;
  const goodsPerType = Number(formula.goodsPerTypePerStep ?? 0) * step;
  const goods = goodsPerType > 0
    ? Object.fromEntries(Object.keys(building.foundationGoods ?? {}).map((resource) => [resource, goodsPerType]))
    : {};
  const resources = Object.fromEntries(
    Object.entries(formula.resourcesPerStep ?? {}).map(([resource, amount]) => [
      resource,
      Number(amount) * step,
    ]),
  );

  return {
    blueprintSets: formula.blueprintSets ?? 1,
    goods,
    resources,
  };
}

function addUnlockCosts(total, addition) {
  total.blueprintSets += addition.blueprintSets;
  for (const group of ["goods", "resources"]) {
    for (const [resource, amount] of Object.entries(addition[group])) {
      total[group][resource] = (total[group][resource] ?? 0) + amount;
    }
  }
}

export function basePositionRewards(p1Reward) {
  if (!Number.isFinite(p1Reward) || p1Reward < 0) {
    throw new TypeError("P1 reward must be a non-negative number");
  }
  const rewards = [p1Reward];
  for (let position = 2; position <= 5; position += 1) {
    const previous = rewards[position - 2];
    rewards.push(forgeHammerRound(previous / position / 5) * 5);
  }
  return rewards;
}

export function baseMedalRewards(p1Reward) {
  if (!Number.isFinite(p1Reward) || p1Reward < 0) {
    throw new TypeError("P1 medal reward must be a non-negative number");
  }
  return [
    p1Reward,
    forgeHammerRound(p1Reward / 2),
    forgeHammerRound(p1Reward / 4),
    forgeHammerRound(p1Reward / 10),
    forgeHammerRound(p1Reward / 20),
  ];
}

export function applyArcBonus(baseRewards, arcBonusPercent) {
  const bonuses = Array.isArray(arcBonusPercent)
    ? arcBonusPercent
    : Array(5).fill(arcBonusPercent);
  if (bonuses.length !== 5 || bonuses.some((bonus) => !Number.isFinite(Number(bonus)))) {
    throw new TypeError("Arc bonus must be one number or an array of five numbers");
  }
  return baseRewards.map((reward, index) =>
    forgeHammerRound(reward * (1 + Number(bonuses[index]) / 100)),
  );
}

function rewardPair(base, arcBonusPercent) {
  return base ? { base, adjusted: applyArcBonus(base, arcBonusPercent) } : null;
}

export function rewardsForLevel(rewardTables, targetLevel, arcBonusPercent = 0) {
  assertTargetLevel(targetLevel);
  const index = targetLevel - 1;
  const fpP1 = rewardTables.fpP1ByLevel?.[index];
  const medalP1 = rewardTables.medalP1ByLevel?.[index];
  const blueprints = rewardTables.blueprintsByLevel?.[index];

  const fpBase = Number.isFinite(fpP1) ? basePositionRewards(fpP1) : null;
  const medalBase = Number.isFinite(medalP1) ? baseMedalRewards(medalP1) : null;
  const blueprintBase =
    Array.isArray(blueprints) &&
    blueprints.length === 5 &&
    blueprints.every((value) => Number.isFinite(value) && value >= 0)
      ? blueprints
      : null;

  return {
    forgePoints: rewardPair(fpBase, arcBonusPercent),
    medals: rewardPair(medalBase, arcBonusPercent),
    blueprints: rewardPair(blueprintBase, arcBonusPercent),
  };
}

export function buildLevelRows(building, rewardTables, arcBonusPercent, maxLevel = MAX_LEVEL) {
  let cumulativeCost = 0;
  const cumulativeUnlockCosts = emptyUnlockCosts();
  const rows = [];
  for (let targetLevel = 1; targetLevel <= maxLevel; targetLevel += 1) {
    const cost = upgradeCost(building.firstTenLevelCosts, targetLevel);
    const unlockCosts = unlockCostsForLevel(building, targetLevel);
    cumulativeCost += cost;
    addUnlockCosts(cumulativeUnlockCosts, unlockCosts);
    rows.push({
      targetLevel,
      cost,
      cumulativeCost,
      unlockCosts,
      cumulativeUnlockCosts: structuredClone(cumulativeUnlockCosts),
      benefits: benefitsForLevel(building, targetLevel),
      rewards: rewardsForLevel(rewardTables, targetLevel, arcBonusPercent),
    });
  }
  return rows;
}

export function buildUpgradeCostSeries(rows) {
  const series = [
    {
      id: "forgePoints",
      values: rows.map((row) => row.cost),
    },
  ];
  const goods = rows.map((row) =>
    Object.values(row.unlockCosts.goods).reduce((total, amount) => total + amount, 0),
  );
  if (goods.some((amount) => amount > 0)) {
    series.push({ id: "goods", values: goods });
  }

  const resourceOrder = ["medals", "money", "supplies", "dark_matter"];
  const resourceKeys = new Set(
    rows.flatMap((row) => Object.keys(row.unlockCosts.resources)),
  );
  const orderedKeys = [...resourceKeys].sort((left, right) => {
    const leftIndex = resourceOrder.indexOf(left);
    const rightIndex = resourceOrder.indexOf(right);
    if (leftIndex < 0 && rightIndex < 0) return left.localeCompare(right);
    if (leftIndex < 0) return 1;
    if (rightIndex < 0) return -1;
    return leftIndex - rightIndex;
  });
  for (const resource of orderedKeys) {
    series.push({
      id: resource,
      values: rows.map((row) => row.unlockCosts.resources[resource] ?? 0),
    });
  }
  return series;
}

export function buildRewardSeries(rows, resource, view = "base") {
  if (!["forgePoints", "medals", "blueprints"].includes(resource)) {
    throw new RangeError(`Unknown reward resource: ${resource}`);
  }
  if (!["base", "adjusted"].includes(view)) {
    throw new RangeError(`Unknown reward view: ${view}`);
  }
  return Array.from({ length: 5 }, (_, position) => ({
    position: position + 1,
    values: rows.map((row) => row.rewards[resource]?.[view][position] ?? null),
  }));
}

export function buildBaseRewardSeries(rows, resource) {
  return buildRewardSeries(rows, resource, "base");
}

export function ownerPrimingCost(totalForgePoints, firstPlaceContribution) {
  if (!Number.isFinite(totalForgePoints) || totalForgePoints < 0) {
    throw new TypeError("Total Forge Point cost must be a non-negative number");
  }
  if (!Number.isFinite(firstPlaceContribution) || firstPlaceContribution < 0) {
    throw new TypeError("First-place contribution must be a non-negative number");
  }
  return Math.max(0, totalForgePoints - firstPlaceContribution * 2);
}

export function buildRageAnalysis(rows, beginningLevel, targetLevel, positionArcBonuses) {
  const maxLevel = Math.max(...rows.map((row) => row.targetLevel));
  assertTargetLevel(beginningLevel, maxLevel);
  assertTargetLevel(targetLevel, maxLevel);
  if (beginningLevel > targetLevel) {
    throw new RangeError("Beginning level cannot be greater than target level");
  }
  if (
    !Array.isArray(positionArcBonuses) ||
    positionArcBonuses.length !== 5 ||
    positionArcBonuses.some((bonus) => {
      const value = Number(bonus);
      return !Number.isFinite(value) || value < 0 || value > 100;
    })
  ) {
    throw new TypeError("Five Arc bonuses between 0% and 100% are required for pre-rage analysis");
  }

  const totals = {
    upgradeForgePoints: 0,
    contributions: [0, 0, 0, 0, 0],
    ownerForgePoints: 0,
    goodsPerType: 0,
    goods: 0,
    money: 0,
    supplies: 0,
    medals: 0,
    specialResources: {},
  };
  const analyzedRows = rows
    .filter(({ targetLevel: level }) => level >= beginningLevel && level <= targetLevel)
    .map((row) => {
      const baseContributions = row.rewards.forgePoints?.base;
      const contributions = baseContributions
        ? applyArcBonus(baseContributions, positionArcBonuses)
        : Array(5).fill(null);
      const contributionTotal = contributions.reduce(
        (sum, amount) => sum + (Number.isFinite(amount) ? amount : 0),
        0,
      );
      const goodsAmounts = Object.values(row.unlockCosts.goods);
      const goods = goodsAmounts.reduce(
        (sum, amount) => sum + amount,
        0,
      );
      const goodsPerType = goodsAmounts.length === 0
        ? 0
        : goodsAmounts.every((amount) => amount === goodsAmounts[0])
          ? goodsAmounts[0]
          : null;
      const specialResources = Object.fromEntries(
        Object.entries(row.unlockCosts.resources).filter(
          ([resource]) => !["money", "supplies", "medals"].includes(resource),
        ),
      );
      const analyzed = {
        targetLevel: row.targetLevel,
        upgradeForgePoints: row.cost,
        contributions,
        ownerForgePoints: Math.max(0, row.cost - contributionTotal),
        goodsPerType,
        goods,
        money: row.unlockCosts.resources.money ?? 0,
        supplies: row.unlockCosts.resources.supplies ?? 0,
        medals: row.unlockCosts.resources.medals ?? 0,
        specialResources,
        benefits: row.benefits ?? [],
      };
      totals.upgradeForgePoints += analyzed.upgradeForgePoints;
      analyzed.contributions.forEach((amount, position) => {
        totals.contributions[position] += Number.isFinite(amount) ? amount : 0;
      });
      if (Number.isFinite(analyzed.goodsPerType)) {
        totals.goodsPerType += analyzed.goodsPerType;
      }
      for (const resource of ["ownerForgePoints", "goods", "money", "supplies", "medals"]) {
        totals[resource] += analyzed[resource];
      }
      for (const [resource, amount] of Object.entries(analyzed.specialResources)) {
        totals.specialResources[resource] =
          (totals.specialResources[resource] ?? 0) + amount;
      }
      return analyzed;
    });

  return { rows: analyzedRows, totals };
}
