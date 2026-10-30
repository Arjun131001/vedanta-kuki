import { test } from "node:test";
import assert from "node:assert/strict";
import { buildOverview, highlightKind, topicFor } from "../src/overview.mjs";
const fact = (label, value, unit = null) => ({
  label,
  source_label: label,
  value,
  unit,
});
test("highlights only explicit reported metrics; no percentages, dates or deposits", () => {
  assert.equal(
    highlightKind(fact("Total consumption", "200823", "kWh")),
    "Energy use",
  );
  assert.equal(highlightKind(fact("Renewable consumption", "32%", "%")), null);
  assert.equal(highlightKind(fact("Security deposit", "100", "INR")), null);
  assert.equal(highlightKind(fact("Bill date", "2024", null)), null);
  assert.equal(
    highlightKind(fact("Current Month Bill", "632023.17", null)),
    "Amount reported",
  );
});
test("counts are per proposal and highlight values remain unchanged", () => {
  const checked = [fact("Water consumption", "1,230", "m3")],
    review = [
      fact("Energy consumption", "42", null),
      fact("Quality commitment", "We protect food safety", null),
    ];
  const result = buildOverview(checked, review);
  assert.equal(result.highlights[0].fact.value, "1,230");
  assert.equal(result.highlights[1].fact.unit, null);
  assert.equal(result.commitments.length, 1);
  assert.equal(
    result.topics.reduce((sum, item) => sum + item.count, 0),
    3,
  );
  assert.equal(topicFor(fact("Waste recycling", "42")), "Waste");
});

test("generic units consumed are not mislabeled as energy", () => {
  const generic = fact("Units Consumed", "2321", "Cubic Meters");
  assert.equal(highlightKind(generic), "Consumption reported");
  assert.notEqual(topicFor(generic), "Energy");
  assert.equal(topicFor(fact("Sewerage Charges", "100", "INR")), "Water");
  assert.equal(topicFor(fact("ETP sludge generated", "42", "kg")), "Waste");
});

test("meter comparison requires one compatible pair without mixing sources", () => {
  const previous = {
    ...fact("Previous Meter Reading", "12500", "Cubic Meters"),
    organization: "Example Water",
  };
  const current = {
    ...fact("Current Meter Reading", "14821", "Cubic Meters"),
    organization: "Example Water",
  };
  const overview = buildOverview([previous, current], []);
  assert.deepEqual(
    overview.meterPair.map((x) => x.fact.value),
    ["12500", "14821"],
  );
  assert.equal(
    buildOverview([previous, { ...current, unit: "kWh" }], []).meterPair,
    null,
  );
  assert.equal(
    buildOverview([previous, { ...current, organization: "Other" }], [])
      .meterPair,
    null,
  );
  assert.equal(
    buildOverview([previous, current, { ...current }], []).meterPair,
    null,
  );
  assert.equal(
    buildOverview([{ ...previous, organization: null }, current], []).meterPair,
    null,
  );
  assert.equal(
    buildOverview([previous, { ...current, value: "about 14821" }], [])
      .meterPair,
    null,
  );
});
