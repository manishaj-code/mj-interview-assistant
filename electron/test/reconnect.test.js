const { test } = require("node:test");
const assert = require("node:assert/strict");
const { nextDelayMs } = require("../reconnect");

test("backoff cap 5s", () => {
  assert.equal(nextDelayMs(0), 500);
  assert.equal(nextDelayMs(1), 1000);
  assert.equal(nextDelayMs(2), 2000);
  assert.equal(nextDelayMs(3), 5000);
  assert.equal(nextDelayMs(99), 5000);
});
