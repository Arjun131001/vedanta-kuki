import test from "node:test";
import assert from "node:assert/strict";
import { displayStatus } from "../src/document-state.mjs";

test("source-ready is Generating until OpenAI finishes", () => {
  assert.equal(displayStatus({ status: "ready", generation_status: "generating" }), "generating");
  assert.equal(displayStatus({ status: "ready", generation_status: "generated" }), "generated");
});
test("generation failure is visible even when source extraction succeeded", () => {
  assert.equal(displayStatus({ status: "ready", generation_status: "failed" }), "failed");
});
test("legacy source-only status remains distinguishable", () => {
  assert.equal(displayStatus({ status: "ready", generation_status: "not_requested" }), "ready");
});
