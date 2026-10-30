export function displayStatus(document) {
  if (document.generation_status === "failed") return "failed";
  if (document.generation_status === "generated") return "generated";
  if (document.generation_status === "generating") return "generating";
  return document.status;
}
