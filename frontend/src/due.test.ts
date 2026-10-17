import { afterEach, describe, expect, test, vi } from "vitest";
import type { Status, Task } from "./api";
import { addDays, dueInput, dueOf, dueToday, instantOf, localDay } from "./due";

type Due = Pick<Task, "due_date" | "due_time" | "due_zone">;
const task = (id: string, due: Partial<Due> | string | null, status: Status = "new") => {
  const fields = typeof due === "string" || due === null ? { due_date: due } : due;
  return { id, title: id, status, due_date: null, due_time: null, due_zone: null, ...fields } as Task;
};
const now = () => new Date(2026, 9, 17, 12, 0); // Saturday, Oct 17, noon here
const label = (due: Partial<Due> | string | null, status: Status = "new", at = now()) => dueOf(task("t", due, status), at, "en-US");

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
  expect(label("2026-10-17")).toEqual({ kind: "today", label: "Today", full: "Saturday, October 17, 2026", note: undefined });
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
  expect(dueToday(tasks, now()).map((t) => t.id)).toEqual(["late", "today"]);
});

// Times are kept in the zone they were set in and shown in this device's: switch the device's zone
// (Node applies TZ as soon as it changes).
describe("times, between Florida and La Palma", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  const florida = "America/New_York";
  const laPalma = "Atlantic/Canary";
  const dentist = { due_date: "2026-10-18", due_time: "15:00", due_zone: florida }; // Sunday 3 pm in Florida
  const late = { due_date: "2026-10-17", due_time: "21:30", due_zone: florida }; // Saturday 9:30 pm in Florida

  test("a clock time in a zone is one moment, summer time or not", () => {
    expect(instantOf("2026-10-18", "15:00", florida).toISOString()).toBe("2026-10-18T19:00:00.000Z"); // EDT
    expect(instantOf("2026-12-18", "15:00", florida).toISOString()).toBe("2026-12-18T20:00:00.000Z"); // EST
    expect(instantOf("2026-10-18", "20:00", laPalma).toISOString()).toBe("2026-10-18T19:00:00.000Z"); // WEST
    expect(instantOf("2026-11-01", "01:30", florida).toISOString()).toBe("2026-11-01T05:30:00.000Z"); // the hour that repeats
    expect(instantOf("2026-10-18", "15:00", "Not/A_Zone").getHours()).toBe(15); // unknown here: this device's clock
  });

  test("in Florida it reads as set", () => {
    vi.stubEnv("TZ", florida);
    const sat = new Date("2026-10-17T16:00:00Z"); // Saturday noon in Florida
    expect(dueOf(task("t", dentist), sat, "en-US", florida)).toEqual({
      kind: "tomorrow", label: "Tomorrow · 3:00 PM", full: "Sunday, October 18, 2026, 3:00 PM", note: undefined,
    });
    expect(dueInput(task("t", dentist))).toEqual({ date: "2026-10-18", time: "15:00" });
  });

  test("in La Palma it reads in La Palma's time, with Florida's in the note", () => {
    vi.stubEnv("TZ", laPalma);
    const sat = new Date("2026-10-17T16:00:00Z"); // Saturday 5 pm in La Palma
    expect(dueOf(task("t", dentist), sat, "en-US", laPalma)).toEqual({
      kind: "tomorrow", label: "Tomorrow · 8:00 PM", full: "Sunday, October 18, 2026, 8:00 PM (3:00 PM New York time)",
      note: "3:00 PM New York time",
    });
    expect(dueInput(task("t", dentist))).toEqual({ date: "2026-10-18", time: "20:00" });
  });

  test("Saturday night in Florida is already Sunday in La Palma", () => {
    vi.stubEnv("TZ", laPalma);
    const sat = new Date("2026-10-17T16:00:00Z");
    expect(dueOf(task("t", late), sat, "en-US", laPalma)).toMatchObject({
      kind: "tomorrow", label: "Tomorrow · 2:30 AM", note: "Sat 9:30 PM New York time",
    });
    expect(dueToday([task("t", late)], sat)).toEqual([]);
    expect(dueToday([task("t", late)], new Date("2026-10-18T09:00:00Z")).map((t) => t.id)).toEqual(["t"]);
  });

  test("a time that has passed is overdue, the same moment everywhere", () => {
    const after = new Date("2026-10-18T19:30:00Z"); // half an hour after the dentist
    vi.stubEnv("TZ", florida);
    expect(dueOf(task("t", dentist), after, "en-US", florida)).toMatchObject({ kind: "overdue", label: "Overdue · 3:00 PM" });
    vi.stubEnv("TZ", laPalma);
    expect(dueOf(task("t", dentist), after, "en-US", laPalma)).toMatchObject({ kind: "overdue", label: "Overdue · 8:00 PM" });
    expect(dueOf(task("t", dentist), new Date("2026-10-19T09:00:00Z"), "en-US", laPalma)).toMatchObject({ label: "Overdue · Oct 18, 8:00 PM" });
    expect(dueOf(task("t", dentist, "done"), after, "en-US", laPalma)).toMatchObject({ kind: "today", label: "Today · 8:00 PM" });
  });
});
