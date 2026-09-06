const MAX_LEVEL = 301;

export function assertTargetLevel(targetLevel, maxLevel = MAX_LEVEL) {
  if (!Number.isInteger(targetLevel) || targetLevel < 1 || targetLevel > maxLevel) {
    throw new RangeError(`Target level must be an integer from 1 to ${maxLevel}`);
  }
}

export function forgeHammerRound(value) {
  const epsilon = 0.000001;
  return Math.round(value + (value >= 0 ? epsilon : -epsilon));
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

export function buildBaseRewardSeries(rows, resource) {
  if (!["forgePoints", "medals", "blueprints"].includes(resource)) {
    throw new RangeError(`Unknown reward resource: ${resource}`);
  }
  return Array.from({ length: 5 }, (_, position) => ({
    position: position + 1,
    values: rows.map((row) => row.rewards[resource]?.base[position] ?? null),
  }));
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
