(function initializeBuildingRankingStrengths(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_STRENGTHS = api;
})(typeof window !== "undefined" ? window : globalThis, function strengthFactory() {
  "use strict";

  const SPECIAL_GOODS_PRODUCTION_ATTR = "prod_resource_special_goods_up_to_age";

  function recordProducesSpecialGoods(record) {
    const value = Number(record?.attrs?.[SPECIAL_GOODS_PRODUCTION_ATTR] || 0);
    return Number.isFinite(value) && value > 0;
  }

  return {
    SPECIAL_GOODS_PRODUCTION_ATTR,
    recordProducesSpecialGoods,
  };
});
