// A task's notes: plain text, where web addresses become links. Only http and https, so a note
// can't make a javascript: link; React escapes everything else.

export const NOTES_MAX = 2000; // as the server; maxLength counts UTF-16 units, so never more than it takes

export type NotePart = { text: string; href?: string };

const ADDRESS = /https?:\/\/[^\s<>"]+/gi;
const TRAILING = /[.,;:!?'"]$/;

// A sentence's full stop, or the bracket around an address, isn't part of it; a bracket that opens
// in the address (Wikipedia's "Mercury_(planet)") is.
function trimEnd(address: string): string {
  for (;;) {
    if (TRAILING.test(address)) address = address.slice(0, -1);
    else if (address.endsWith(")") && address.split("(").length < address.split(")").length) address = address.slice(0, -1);
    else return address;
  }
}

export function noteParts(text: string): NotePart[] {
  const parts: NotePart[] = [];
  let from = 0;
  for (const match of text.matchAll(ADDRESS)) {
    const address = trimEnd(match[0]);
    if (!/^https?:\/\/./i.test(address)) continue;
    if (match.index > from) parts.push({ text: text.slice(from, match.index) });
    parts.push({ text: address, href: address });
    from = match.index + address.length;
  }
  if (from < text.length) parts.push({ text: text.slice(from) });
  return parts;
}
