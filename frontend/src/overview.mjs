/** Derive navigation counts and conservative highlights from saved proposals only. */
export function topicFor(fact) {
  const text = `${fact.label || ""} ${fact.source_label || ""}`.toLowerCase();
  if (/\b(water|wastewater|sewage|sewerage|effluent)\b/.test(text))
    return "Water";
  if (/\b(waste|sludge|recycl|landfill|disposal)\w*/.test(text)) return "Waste";
  if (/\b(emission|carbon|co2|ghg)\w*/.test(text)) return "Emissions";
  if (/\b(policy|commitment|safety|quality|customer|compliance)\w*/.test(text))
    return "Policy";
  if (
    /\b(energy|electric|power|kwh|mwh|grid|solar|wind)\w*/.test(text) ||
    /^(?:kwh|mwh|gwh)$/i.test((fact.unit || "").trim())
  )
    return "Energy";
  if (/\b(consumption|consumed|meter|reading)\w*/.test(text))
    return "Consumption";
  if (/\b(bill|payable|invoice|amount due|amount payable)\w*/.test(text))
    return "Billing";
  return "Other";
}

export function highlightKind(fact) {
  const label = `${fact.label || ""} ${fact.source_label || ""}`.toLowerCase();
  const value = String(fact.value ?? "").trim();
  if (
    /\b(account|phone|address|date|billing period|bill month|reporting period|meter number|bill number|security deposit|previous outstanding|customer id)\b/.test(
      label,
    )
  )
    return null;
  if (/%/.test(value) || (fact.unit || "").trim() === "%") return null;
  if (!/^[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(value)) return null;
  if (
    /\b(water|effluent|sewage)\b/.test(label) &&
    /\b(consumption|usage|used|quantity|volume|units)\b/.test(label)
  )
    return "Water use";
  if (
    /\b(waste|sludge|recycl)\w*/.test(label) &&
    /\b(quantity|weight|amount|total|generated)\b/.test(label)
  )
    return "Waste";
  if (
    /\b(current month bill|current bill|amount payable|payable amount|total due|amount due|net payable)\b/.test(
      label,
    )
  )
    return "Amount reported";
  if (
    /\b(consumption|consumed|energy used|electricity used|grid supply)\b/.test(
      label,
    )
  ) {
    const energy =
      /\b(energy|electric|grid|power|solar|wind)\w*/.test(label) ||
      /^(?:kwh|mwh|gwh)$/i.test((fact.unit || "").trim());
    return energy ? "Energy use" : "Consumption reported";
  }
  return null;
}

export function findMeterPair(checked, review) {
  const all = [
    ...checked.map((fact) => ({ fact, status: "checked" })),
    ...review.map((fact) => ({ fact, status: "review" })),
  ];
  const previous = [],
    current = [];
  for (const item of all) {
    const label =
      `${item.fact.label || ""} ${item.fact.source_label || ""}`.toLowerCase();
    if (
      /\b(date|account|number|id|difference|consumption)\b/.test(label) ||
      !/\breading\b/.test(label)
    )
      continue;
    const value = String(item.fact.value ?? "").trim();
    if (!/^(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(value)) continue;
    const numeric = Number(value.replace(/,/g, ""));
    if (!Number.isFinite(numeric)) continue;
    if (/\b(previous|prior)\b/.test(label)) previous.push({ ...item, numeric });
    else if (/\b(current|present)\b/.test(label))
      current.push({ ...item, numeric });
  }
  if (previous.length !== 1 || current.length !== 1) return null;
  const a = previous[0],
    b = current[0];
  if (
    !a.fact.organization ||
    !b.fact.organization ||
    a.fact.organization !== b.fact.organization ||
    !a.fact.unit ||
    a.fact.unit !== b.fact.unit
  )
    return null;
  return [a, b];
}

export function buildOverview(checked, review) {
  const all = [
    ...checked.map((fact) => ({ fact, status: "checked" })),
    ...review.map((fact) => ({ fact, status: "review" })),
  ];
  const counts = new Map();
  for (const item of all) {
    const topic = topicFor(item.fact);
    counts.set(topic, (counts.get(topic) || 0) + 1);
  }
  const topics = [...counts]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  const highlights = [];
  const kinds = new Set();
  for (const item of all) {
    const kind = highlightKind(item.fact);
    if (kind && !kinds.has(kind)) {
      highlights.push({ ...item, kind });
      kinds.add(kind);
    }
    if (highlights.length === 4) break;
  }
  const commitments = all.filter(
    ({ fact }) =>
      topicFor(fact) === "Policy" &&
      !/^[-+\d.,% ]+$/.test(String(fact.value || "")),
  );
  return {
    topics,
    highlights,
    commitments,
    meterPair: findMeterPair(checked, review),
  };
}
