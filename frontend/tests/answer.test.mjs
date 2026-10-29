import test from "node:test";
import assert from "node:assert/strict";
import { parseAnswer, parseInline } from "../src/answer.mjs";
test("groups paragraphs, headings and consecutive list items", () => {
  assert.deepEqual(parseAnswer("## Summary\nHello\nworld\n\n- One\n- Two\n1. Three"), [
    { type: "heading", text: "Summary" }, { type: "paragraph", text: "Hello\nworld" },
    { type: "unordered", items: ["One", "Two"] }, { type: "ordered", items: ["Three"] },
  ]);
});
test("only valid citation indices become links; markup remains literal text", () => {
  assert.deepEqual(parseInline("<img> **Important** [1] [9] [0]", 1), [
    { type: "text", text: "<img> " }, { type: "bold", text: "Important" }, { type: "text", text: " " },
    { type: "citation", index: 1, text: "[1]" }, { type: "text", text: " " }, { type: "text", text: "[9]" },
    { type: "text", text: " " }, { type: "text", text: "[0]" },
  ]);
});
