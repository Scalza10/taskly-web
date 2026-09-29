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

test("nothing when there are no lists", () => {
  expect(pickList([], "a")).toBeNull();
});
