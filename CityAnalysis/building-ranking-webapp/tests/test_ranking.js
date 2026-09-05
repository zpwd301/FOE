const test = require("node:test");
const assert = require("node:assert/strict");

const {
  rankRows,
  rankRowsAgainstBenchmark,
} = require("../src/ranking.js");

function row(entityId, name, rankValue) {
  return { record: { entityId, name }, rankValue };
}

test("sorts rows by ranking value and assigns sequential ranks", () => {
  const rows = [
    row("third", "Third", 70),
    row("first", "First", 90),
    row("second", "Second", 80),
  ];

  rankRows(rows);

  assert.deepEqual(
    rows.map((item) => [item.record.entityId, item.rank]),
    [["first", 1], ["second", 2], ["third", 3]]
  );
});

test("assigns unique benchmark-relative ranks to placed-age rows in the same benchmark gap", () => {
  const benchmarkRows = [
    row("a", "A", 100),
    row("b", "B", 90),
    row("c", "C", 80),
    row("ironclad", "Ironclad Depot - Lv. 2", 60),
    row("windmill", "Bougainvillea Windmill", 50),
    row("d", "D", 40),
  ];
  const placedRows = [
    row("windmill", "Bougainvillea Windmill", 74),
    row("ironclad", "Ironclad Depot - Lv. 2", 75),
  ];

  rankRows(benchmarkRows);
  rankRowsAgainstBenchmark(placedRows, benchmarkRows);

  assert.deepEqual(
    placedRows.map((item) => [item.record.entityId, item.rank]),
    [["ironclad", 4], ["windmill", 5]]
  );
  assert.equal(new Set(placedRows.map((item) => item.rank)).size, placedRows.length);
});
