const test = require("node:test");
const assert = require("node:assert/strict");

const {
  detailAttributeLabel,
  outputsForAttribute,
  probabilityLabel,
} = require("../src/unit-production.js");

test("adds a single unit class to the detail attribute label", () => {
  const production = [
    { attributeKey: "prod_unit_next_age", classLabel: "Ranged" },
  ];

  assert.equal(
    detailAttributeLabel("Next Age Unit", "prod_unit_next_age", production),
    "Next Age Units — Ranged"
  );
});

test("uses Mixed when an attribute produces multiple unit classes", () => {
  const production = [
    { attributeKey: "prod_unit_next_age", classLabel: "Heavy" },
    { attributeKey: "prod_unit_next_age", classLabel: "Ranged" },
  ];

  assert.equal(
    detailAttributeLabel("Next Age Unit", "prod_unit_next_age", production),
    "Next Age Units — Mixed"
  );
});

test("filters structured unit output by ranking attribute", () => {
  const production = [
    { attributeKey: "prod_unit_current_age", unitName: "Nail Storm" },
    { attributeKey: "prod_unit_next_age", unitName: "Ghost Blaster" },
  ];

  assert.deepEqual(
    outputsForAttribute(production, "prod_unit_next_age").map((item) => item.unitName),
    ["Ghost Blaster"]
  );
  assert.equal(probabilityLabel(0.35), "35%");
});
