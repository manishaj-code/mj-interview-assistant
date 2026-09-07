const { test } = require("node:test");
const assert = require("node:assert/strict");
const { createStore } = require("../renderer/overlayStore");

test("status enables start", () => {
  const s = createStore();
  s.apply({ type: "status", payload: { state: "idle", warnings: [], missing_api_key: false } });
  assert.equal(s.get().startEnabled, true);
  assert.equal(s.get().status, "idle");
});

test("seq 1 clears answer then appends", () => {
  const s = createStore();
  s.apply({ type: "answer_token", payload: { token: "Hello", seq: 1 } });
  s.apply({ type: "answer_token", payload: { token: " world", seq: 2 } });
  assert.equal(s.get().answer, "Hello world");
  s.apply({ type: "answer_token", payload: { token: "New", seq: 1 } });
  assert.equal(s.get().answer, "New");
});

test("error sets banner", () => {
  const s = createStore();
  s.apply({ type: "error", payload: { code: "LLM_TIMEOUT", message: "timed out", fatal: false } });
  assert.equal(s.get().error, "timed out");
});

test("question_detected sets question", () => {
  const s = createStore();
  s.apply({ type: "answer_token", payload: { token: "Old", seq: 1 } });
  s.apply({ type: "question_detected", payload: { question_text: "Why us?", timestamp: 1 } });
  assert.equal(s.get().question, "Why us?");
  assert.equal(s.get().answer, "Old");
});
