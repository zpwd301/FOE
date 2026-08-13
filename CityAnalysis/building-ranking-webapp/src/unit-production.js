(function initializeBuildingRankingUnitProduction(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_UNIT_PRODUCTION = api;
})(typeof window !== "undefined" ? window : globalThis, function unitProductionFactory() {
  "use strict";

  const UNIT_ATTRIBUTE_LABELS = {
    prod_unit_current_age: "Current Age Units",
    prod_unit_next_age: "Next Age Units",
    prod_unit_rogue: "Rogues",
  };

  function outputsForAttribute(production, attributeKey) {
    if (!Array.isArray(production)) return [];
    return production.filter((item) => item?.attributeKey === attributeKey);
  }

  function detailAttributeLabel(baseLabel, attributeKey, production) {
    const unitLabel = UNIT_ATTRIBUTE_LABELS[attributeKey];
    if (!unitLabel) return baseLabel;
    const outputs = outputsForAttribute(production, attributeKey);
    const knownClasses = [...new Set(outputs.map((item) => item.classLabel).filter(Boolean))];
    const hasUnknownClass = outputs.some((item) => !item.classLabel);
    if (knownClasses.length === 1 && !hasUnknownClass) return `${unitLabel} — ${knownClasses[0]}`;
    if (knownClasses.length > 1 || (knownClasses.length && hasUnknownClass)) return `${unitLabel} — Mixed`;
    return unitLabel;
  }

  function probabilityLabel(chance) {
    const percentage = Number(chance) * 100;
    return `${percentage.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  }

  return {
    detailAttributeLabel,
    outputsForAttribute,
    probabilityLabel,
  };
});
