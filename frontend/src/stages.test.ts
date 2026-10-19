import { expect, test } from "vitest";
import type { Status, Task } from "./api";
import { focusTask, headline, stage, statusChange, todayHeadline, workingOn } from "./stages";

const task = (title: string, status: Status) => ({ id: title, title, status }) as Task;

test("the headline counts the tasks not done, in words up to nine", () => {
  expect(headline([])).toBe("All clear.");
  expect(headline([task("a", "done")])).toBe("All clear.");
  expect(headline([task("a", "progress"), task("b", "done")])).toBe("One thing to tend to.");
  expect(headline([task("a", "new"), task("b", "progress")])).toBe("Two things to tend to.");
  expect(headline(Array.from({ length: 9 }, (_, i) => task(`${i}`, "new")))).toBe("Nine things to tend to.");
  expect(headline(Array.from({ length: 10 }, (_, i) => task(`${i}`, "new")))).toBe("10 things to tend to.");
});

test("the Today screen's headline counts what's left for today", () => {
  expect(todayHeadline(0)).toBe("All clear today.");
  expect(todayHeadline(1)).toBe("One thing for today.");
  expect(todayHeadline(4)).toBe("Four things for today.");
  expect(todayHeadline(12)).toBe("12 things for today.");
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

test("moving a task to another stage changes its status; to its own, nothing", () => {
  expect(statusChange(task("a", "new"), "done")).toEqual({ method: "PATCH", path: "/api/tasks/a", body: { status: "done" } });
  expect(statusChange(task("a", "done"), "progress")).toEqual({ method: "PATCH", path: "/api/tasks/a", body: { status: "progress" } });
  expect(statusChange(task("a", "progress"), "progress")).toBeUndefined();
});

test("finishing a repeating task names the next one and the day it was finished", () => {
  const now = new Date("2026-10-21T02:30:00Z");
  const weekly = { ...task("a", "progress"), due_date: "2026-10-19", repeat: "FREQ=WEEKLY;BYDAY=MO" } as Task;
  const finish = statusChange(weekly, "done", now)!.body as { status: string; next_id: string; finished_on: string };
  expect(finish.status).toBe("done");
  expect(finish.next_id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  expect(finish.finished_on).toBe(`2026-10-${String(now.getDate()).padStart(2, "0")}`); // this device's day
  // With a time: the day where it's due, as its date and rule are.
  const timed = { ...weekly, due_time: "09:00", due_zone: "America/Los_Angeles" };
  expect((statusChange(timed, "done", now)!.body as { finished_on: string }).finished_on).toBe("2026-10-20");
  // Not when it's only moving along, or isn't repeating.
  expect(statusChange(weekly, "new", now)!.body).toEqual({ status: "new" });
  expect(statusChange(task("b", "new"), "done", now)!.body).toEqual({ status: "done" });
});

test("the Focus screen's task: the one picked if it's open in this list, else the one working on", () => {
  const tasks = [task("a", "new"), task("b", "progress"), task("c", "done")];
  expect(focusTask(tasks, "a")?.title).toBe("a");
  expect(focusTask(tasks, null)?.title).toBe("b");
  expect(focusTask(tasks, "c")?.title).toBe("b"); // done
  expect(focusTask(tasks, "other-list")?.title).toBe("b");
  expect(focusTask([task("c", "done")], "c")).toBeUndefined();
});
