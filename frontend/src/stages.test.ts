import { expect, test } from "vitest";
import type { Status, Task } from "./api";
import { headline, stage, workingOn } from "./stages";

const task = (title: string, status: Status) => ({ title, status }) as Task;

test("the headline counts the tasks not done, in words up to nine", () => {
  expect(headline([])).toBe("All clear.");
  expect(headline([task("a", "done")])).toBe("All clear.");
  expect(headline([task("a", "progress"), task("b", "done")])).toBe("One thing to tend to.");
  expect(headline([task("a", "new"), task("b", "progress")])).toBe("Two things to tend to.");
  expect(headline(Array.from({ length: 9 }, (_, i) => task(`${i}`, "new")))).toBe("Nine things to tend to.");
  expect(headline(Array.from({ length: 10 }, (_, i) => task(`${i}`, "new")))).toBe("10 things to tend to.");
});

test("the board moves a task new → in progress → done → new", () => {
  expect(stage("new")).toMatchObject({ label: "New", action: "Start", next: "progress" });
  expect(stage("progress")).toMatchObject({ label: "In progress", action: "Finish", next: "done" });
  expect(stage("done")).toMatchObject({ label: "Done", action: "Reopen", next: "new" });
});

test("working on: the first task in progress, else the first new one", () => {
  expect(workingOn([task("a", "new"), task("b", "progress"), task("c", "progress")])?.title).toBe("b");
  expect(workingOn([task("a", "done"), task("b", "new")])?.title).toBe("b");
  expect(workingOn([task("a", "done")])).toBeUndefined();
});
