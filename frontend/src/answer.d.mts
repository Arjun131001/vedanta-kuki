export type AnswerBlock = { type: "paragraph"; text: string } | { type: "heading"; text: string } | { type: "ordered"; items: string[] } | { type: "unordered"; items: string[] };
export type InlinePart = { type: "text" | "bold"; text: string } | { type: "citation"; text: string; index: number };
export function parseAnswer(text: string): AnswerBlock[];
export function parseInline(text: string, citationCount: number): InlinePart[];
