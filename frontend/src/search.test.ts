import { expect, test } from "vitest";
import type { Status, Task, TaskList } from "./api";
import { searchTasks } from "./search";

const task = (id: string, title: string, status: Status = "new") => ({ id, title, status }) as Task;
const list = (id: string, name: string, tasks: Task[]) => ({ id, name, tasks }) as TaskList;

const lists = [
  list("g", "Groceries", [task("1", "Oat milk"), task("2", "Bread"), task("3", "Milk chocolate", "done")]),
  list("w", "Work", [task("4", "Email Milan about the café"), task("5", "Plan the week", "progress")]),
  list("e", "Empty", []),
];
const found = (query: string) => searchTasks(lists, query).map((g) => [g.list.name, g.tasks.map((t) => t.id)]);

test("an empty query finds nothing", () => {
  expect(searchTasks(lists, "")).toEqual([]);
  expect(searchTasks(lists, "   ")).toEqual([]);
});

test("matches across every list, grouped by list, in the lists' order; lists without a match are left out", () => {
  expect(found("mil")).toEqual([["Groceries", ["1", "3"]], ["Work", ["4"]]]);
});

test("case and accents don't matter, either way round", () => {
  expect(found("CAFE")).toEqual([["Work", ["4"]]]);
  expect(found("café")).toEqual([["Work", ["4"]]]);
  expect(searchTasks([list("x", "X", [task("6", "Cafe")])], "CAFÉ")[0].tasks[0].id).toBe("6");
});

test("every word must match, in any order", () => {
  expect(found("milk oat")).toEqual([["Groceries", ["1"]]]);
  expect(found("milk  bread")).toEqual([]);
});

test("done tasks are found too, in the list's order (done ones last)", () => {
  expect(found("chocolate")).toEqual([["Groceries", ["3"]]]);
});
