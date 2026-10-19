import { expect, test } from "vitest";
import { pickList } from "./pickList";

const lists = [{ id: "a" }, { id: "b" }];

test("the remembered list when it still exists", () => {
  expect(pickList(lists, "b")).toBe("b");
});

test("the first list when the remembered one is gone or there is none", () => {
  expect(pickList(lists, "deleted")).toBe("a");
  expect(pickList(lists, null)).toBe("a");
});

test("the first of several remembered lists that still exists", () => {
  // The Today screen's add bar: its own pick, then the List screen's, then the first list.
  expect(pickList(lists, "b", "a")).toBe("b");
  expect(pickList(lists, "deleted", "b")).toBe("b");
  expect(pickList(lists, null, "b")).toBe("b");
  expect(pickList(lists, "deleted", null)).toBe("a");
});

test("nothing when there are no lists", () => {
  expect(pickList([], "a")).toBeNull();
});
