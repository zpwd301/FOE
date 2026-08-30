const test = require("node:test");
const assert = require("node:assert/strict");

const {
  OPTIONS,
  optionForKey,
  productionValue,
  recordMatches,
} = require("../src/production-search.js");

test("offers the requested production searches without Forge Points", () => {
  assert.deepEqual(
    OPTIONS.map((option) => option.label),
    [
      "Next-age goods",
      "Next-age units/troops",
      "Blueprints - Current and Higher Age",
      "Blueprints - Random",
      "Current-age goods",
      "Current-age units/troops",
      "Diamonds",
    ]
  );
  assert.equal(OPTIONS.some((option) => /forge points/i.test(option.label)), false);
});

test("keeps current-or-higher and random blueprints distinct", () => {
  const record = {
    attrs: {
      prod_resource_blueprint: 12,
      prod_resource_blueprint_current_or_higher_age: 9,
      prod_resource_blueprint_random: 3,
    },
  };

  assert.equal(productionValue(record, "blueprints-current-or-higher"), 9);
  assert.equal(productionValue(record, "blueprints-random"), 3);
  assert.equal(recordMatches(record, "blueprints-current-or-higher"), true);
  assert.equal(optionForKey("blueprints-random").unit, "blueprints/day");
});

test("rejects missing and unknown production values", () => {
  assert.equal(recordMatches({ attrs: {} }, "next-age-goods"), false);
  assert.equal(recordMatches({ attrs: { prod_unit_next_age: 4 } }, "unknown"), false);
});
