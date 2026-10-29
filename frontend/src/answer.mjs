export function parseAnswer(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const blocks = [];
  let paragraph = [];
  const flush = () => { if (paragraph.length) { blocks.push({ type: "paragraph", text: paragraph.join("\n") }); paragraph = []; } };
  for (const line of lines) {
    const heading = line.match(/^\s{0,3}#{1,3}\s+(.+)$/);
    const item = line.match(/^\s*(?:([-*])\s+|(\d+)[.)]\s+)(.+)$/);
    if (heading) { flush(); blocks.push({ type: "heading", text: heading[1] }); }
    else if (item) { flush(); const type = item[2] ? "ordered" : "unordered"; const last = blocks[blocks.length - 1]; if (last?.type === type) last.items.push(item[3]); else blocks.push({ type, items: [item[3]] }); }
    else if (!line.trim()) flush();
    else paragraph.push(line);
  }
  flush();
  return blocks;
}
export function parseInline(text, citationCount) {
  const parts = []; const pattern = /\*\*([^*\n]+)\*\*|\[(\d+)\]/g; let last = 0; let match;
  while ((match = pattern.exec(text))) {
    if (match.index > last) parts.push({ type: "text", text: text.slice(last, match.index) });
    const index = Number(match[2]);
    if (match[1]) parts.push({ type: "bold", text: match[1] });
    else if (index > 0 && index <= citationCount) parts.push({ type: "citation", index, text: match[0] });
    else parts.push({ type: "text", text: match[0] });
    last = pattern.lastIndex;
  }
  if (last < text.length) parts.push({ type: "text", text: text.slice(last) });
  return parts;
}
