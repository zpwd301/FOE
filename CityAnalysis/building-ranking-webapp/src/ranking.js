(function initializeRanking(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  if (root) root.FOE_BUILDING_RANKING_RANKING = api;
})(typeof window !== "undefined" ? window : globalThis, function rankingFactory() {
  "use strict";

  function rankingOrder(left, right) {
    return right.rankValue - left.rankValue || left.record.name.localeCompare(right.record.name);
  }

  function rankRows(rows) {
    rows.sort(rankingOrder);
    rows.forEach((row, index) => { row.rank = index + 1; });
    return rows;
  }

  function rankRowsAgainstBenchmark(rows, benchmarkRows) {
    const placedEntityIds = new Set(rows.map((row) => row.record.entityId));
    const comparisonRows = benchmarkRows
      .filter((row) => !placedEntityIds.has(row.record.entityId))
      .map((row) => ({ ...row }));
    comparisonRows.push(...rows);
    rankRows(comparisonRows);
    rows.sort(rankingOrder);
    return rows;
  }

  return {
    rankRows,
    rankRowsAgainstBenchmark,
    rankingOrder,
  };
});
