import { expect, test } from "vitest";

// The page's sources are UTF-8. A tool that reads one in the Windows code page and writes it back
// turns "·" into "Â·" and "×" into "Ã—" on the screen (TaskItem.tsx shipped that way once).
const sources = import.meta.glob("./**/*.{ts,tsx,css,html}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
// UTF-8's lead bytes read as Windows-1252: Â or Ã then a continuation, or â€ (curly quotes, dashes).
const GARBLED = /[ÂÃ][\u0080-¿Œ-Ÿˆ-›€™]|â€/;

test("no source file has text garbled by the wrong encoding", () => {
  expect(Object.keys(sources).length).toBeGreaterThan(20);
  expect(Object.entries(sources).filter(([, text]) => GARBLED.test(text)).map(([path]) => path)).toEqual([]);
});
