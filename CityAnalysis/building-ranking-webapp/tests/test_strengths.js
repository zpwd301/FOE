const test = require("node:test");
const assert = require("node:assert/strict");

const {
  SPECIAL_GOODS_PRODUCTION_ATTR,
  recordProducesSpecialGoods,
} = require("../src/strengths.js");

test("direct special-goods production matches the strength filter", () => {
  const record = { attrs: { [SPECIAL_GOODS_PRODUCTION_ATTR]: 45 } };

  assert.equal(recordProducesSpecialGoods(record), true);
});

test("zero and missing special-goods production do not match", () => {
  assert.equal(recordProducesSpecialGoods({ attrs: { [SPECIAL_GOODS_PRODUCTION_ATTR]: 0 } }), false);
  assert.equal(recordProducesSpecialGoods({ attrs: {} }), false);
  assert.equal(recordProducesSpecialGoods(null), false);
});

test("regular goods and special-goods boosts alone do not match", () => {
  const record = {
    attrs: {
      prod_resource_goods_total: 500,
      boost_special_goods_production_all: 25,
    },
  };

  assert.equal(recordProducesSpecialGoods(record), false);
});
