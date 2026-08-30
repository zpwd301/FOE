(function initializeBuildingRankingProductionSearch(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_PRODUCTION_SEARCH = api;
})(typeof window !== "undefined" ? window : globalThis, function productionSearchFactory() {
  "use strict";

  const OPTIONS = [
    {
      key: "next-age-goods",
      label: "Next-age goods",
      attributeKey: "prod_resource_all_goods_of_next_age",
      unit: "goods/day",
    },
    {
      key: "next-age-units",
      label: "Next-age units/troops",
      attributeKey: "prod_unit_next_age",
      unit: "units/day",
    },
    {
      key: "blueprints-current-or-higher",
      label: "Blueprints - Current and Higher Age",
      attributeKey: "prod_resource_blueprint_current_or_higher_age",
      unit: "blueprints/day",
    },
    {
      key: "blueprints-random",
      label: "Blueprints - Random",
      attributeKey: "prod_resource_blueprint_random",
      unit: "blueprints/day",
    },
    {
      key: "current-age-goods",
      label: "Current-age goods",
      attributeKey: "prod_resource_all_goods_of_age",
      unit: "goods/day",
    },
    {
      key: "current-age-units",
      label: "Current-age units/troops",
      attributeKey: "prod_unit_current_age",
      unit: "units/day",
    },
    {
      key: "diamonds",
      label: "Diamonds",
      attributeKey: "prod_resource_premium",
      unit: "diamonds/day",
    },
  ];

  const OPTION_BY_KEY = Object.fromEntries(OPTIONS.map((option) => [option.key, option]));

  function optionForKey(key) {
    return OPTION_BY_KEY[key] || null;
  }

  function productionValue(record, key) {
    const option = optionForKey(key);
    if (!option) return 0;
    return Number(record?.attrs?.[option.attributeKey] || 0);
  }

  function recordMatches(record, key) {
    return productionValue(record, key) > 0;
  }

  return {
    OPTIONS,
    optionForKey,
    productionValue,
    recordMatches,
  };
});
