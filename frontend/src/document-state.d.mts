export function displayStatus(document: {
  status: "queued" | "processing" | "ready" | "failed";
  generation_status?: "not_requested" | "generating" | "generated" | "failed";
}): "queued" | "processing" | "ready" | "failed" | "generating" | "generated";
