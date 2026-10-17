import { expect, test } from "vitest";
import type { Status, Task } from "./api";
import { addDays, dueOf, dueToday, localDay } from "./due";

const task = (id: string, due_date: string | null, status: Status = "new") => ({ id, title: id, status, due_date }) as Task;
const today = "2026-10-17"; // a Saturday
const label = (due_date: string | null, status: Status = "new") => dueOf(task("t", due_date, status), today, "en-US");

test("the device's date, as a calendar day", () => {
  expect(localDay(new Date(2026, 9, 17, 0, 0))).toBe("2026-10-17");
  expect(localDay(new Date(2026, 9, 17, 23, 59))).toBe("2026-10-17");
  expect(localDay(new Date(2026, 0, 5))).toBe("2026-01-05");
});

test("adding days crosses months and years", () => {
  expect(addDays("2026-10-17", 1)).toBe("2026-10-18");
  expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
  expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  expect(addDays("2026-03-08", 7)).toBe("2026-03-15");
});

test("no due date, no chip", () => {
  expect(label(null)).toBeUndefined();
});

test("today and tomorrow by name", () => {
  expect(label("2026-10-17")).toEqual({ kind: "today", label: "Today", full: "Saturday, October 17, 2026" });
  expect(label("2026-10-18")).toMatchObject({ kind: "tomorrow", label: "Tomorrow" });
});

test("before today is overdue, unless it's done", () => {
  expect(label("2026-10-15")).toMatchObject({ kind: "overdue", label: "Overdue · Oct 15" });
  expect(label("2026-10-16", "progress")).toMatchObject({ kind: "overdue", label: "Overdue · Oct 16" });
  expect(label("2026-10-15", "done")).toMatchObject({ kind: "date", label: "Oct 15" });
  expect(label("2025-12-24")).toMatchObject({ kind: "overdue", label: "Overdue · Dec 24, 2025" });
});

test("the coming week by weekday, later ones by date, another year with it", () => {
  expect(label("2026-10-19")).toMatchObject({ kind: "date", label: "Mon, Oct 19" });
  expect(label("2026-10-23")).toMatchObject({ kind: "date", label: "Fri, Oct 23" });
  expect(label("2026-10-24")).toMatchObject({ kind: "date", label: "Oct 24" });
  expect(label("2027-01-05")).toMatchObject({ kind: "date", label: "Jan 5, 2027" });
});

test("due today keeps the open tasks due today or before, in their order", () => {
  const tasks = [
    task("late", "2026-10-10"),
    task("none", null),
    task("today", "2026-10-17", "progress"),
    task("tomorrow", "2026-10-18"),
    task("done-today", "2026-10-17", "done"),
  ];
  expect(dueToday(tasks, today).map((t) => t.id)).toEqual(["late", "today"]);
});
