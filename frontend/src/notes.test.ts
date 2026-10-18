import { expect, test } from "vitest";
import { noteParts } from "./notes";

test("plain text is one part", () => {
  expect(noteParts("Call first\nask for Sam")).toEqual([{ text: "Call first\nask for Sam" }]);
  expect(noteParts("")).toEqual([]);
});

test("a web address is a link; the text around it stays", () => {
  expect(noteParts("Specs: https://example.com/a?b=1#c and more")).toEqual([
    { text: "Specs: " },
    { text: "https://example.com/a?b=1#c", href: "https://example.com/a?b=1#c" },
    { text: " and more" },
  ]);
});

test("punctuation that ends a sentence isn't part of the link", () => {
  expect(noteParts("See http://example.com/x.")).toEqual([
    { text: "See " },
    { text: "http://example.com/x", href: "http://example.com/x" },
    { text: "." },
  ]);
  expect(noteParts("(https://example.com/y), then")).toEqual([
    { text: "(" },
    { text: "https://example.com/y", href: "https://example.com/y" },
    { text: "), then" },
  ]);
});

test("brackets that belong to the address stay in it", () => {
  const wiki = "https://en.wikipedia.org/wiki/Mercury_(planet)";
  expect(noteParts(`${wiki} is it`)).toEqual([{ text: wiki, href: wiki }, { text: " is it" }]);
});

test("two links, one per line", () => {
  expect(noteParts("https://a.example\nhttps://b.example")).toEqual([
    { text: "https://a.example", href: "https://a.example" },
    { text: "\n" },
    { text: "https://b.example", href: "https://b.example" },
  ]);
});

test("only http and https are links, in any case", () => {
  expect(noteParts("javascript:alert(1) ftp://example.com mailto:a@b.c")).toEqual([{ text: "javascript:alert(1) ftp://example.com mailto:a@b.c" }]);
  expect(noteParts("HTTPS://EXAMPLE.COM")).toEqual([{ text: "HTTPS://EXAMPLE.COM", href: "HTTPS://EXAMPLE.COM" }]);
  expect(noteParts("https:// nothing")).toEqual([{ text: "https:// nothing" }]);
});
