import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Snapshot, Task, TaskList } from "./api";
import { todayView, type Entry } from "./today";
import { applyQueue } from "./view";

const florida = "America/New_York";
// Monday, Oct 19, 2026, 10 am in Florida, where this device is.
const now = new Date("2026-10-19T14:00:00Z");

beforeEach(() => vi.stubEnv("TZ", florida));
afterEach(() => vi.unstubAllEnvs());

function task(id: string, extra: Partial<Task> = {}): Task {
  return {
    id, list_id: "", title: id, status: "new", done: false, due_date: null, due_time: null, due_zone: null, notes: null, repeat: null, starred: false,
    created_by: "maria", done_by: null, created_at: "2026-10-01T12:00:00Z", updated_at: "2026-10-01T12:00:00Z", ...extra,
  };
}
const list = (name: string, tasks: Task[]): TaskList =>
  ({ id: name, name, owner: "maria", role: "owner", members: ["maria"], tasks: tasks.map((t) => ({ ...t, list_id: name })) });
const ids = (entries: Entry[]) => entries.map((entry) => entry.task.id);
const done = (id: string, updated_at: string, extra: Partial<Task> = {}) => task(id, { status: "done", done: true, done_by: "maria", updated_at, ...extra });

test("overdue, due today and in progress, from every list; tomorrow's and the rest stay out", () => {
  const home = list("Home", [
    task("yesterday", { due_date: "2026-10-18" }),
    task("passed", { due_date: "2026-10-19", due_time: "08:00", due_zone: florida }), // its chip says overdue too
    task("later", { due_date: "2026-10-19", due_time: "15:00", due_zone: florida }),
    task("today", { due_date: "2026-10-19" }),
    task("tomorrow", { due_date: "2026-10-20" }),
    task("someday"),
  ]);
  const work = list("Work", [
    task("started", { status: "progress" }),
    task("started-tomorrow", { status: "progress", due_date: "2026-10-20" }),
    task("started-today", { status: "progress", due_date: "2026-10-19" }),
    task("started-late", { status: "progress", due_date: "2026-10-12" }),
  ]);

  const view = todayView([home, work], now);

  expect(ids(view.overdue)).toEqual(["started-late", "yesterday", "passed"]); // oldest first
  expect(ids(view.today)).toEqual(["later", "today", "started-today"]); // times in order, then the days
  expect(ids(view.progress)).toEqual(["started-tomorrow", "started"]); // each task once: due ones first
  expect(view.done).toEqual([]);
  expect(view.today.map((entry) => entry.list.name)).toEqual(["Home", "Home", "Work"]);
});

test("starred: every open starred task, whatever its date, and only there", () => {
  const home = list("Home", [
    task("yesterday", { due_date: "2026-10-18" }),
    task("starred-overdue", { due_date: "2026-10-18", starred: true }),
    task("starred-today", { due_date: "2026-10-19", starred: true }),
    task("starred-next-week", { due_date: "2026-10-26", starred: true }),
    task("starred-someday", { starred: true }),
    task("someday"),
  ]);
  const work = list("Work", [
    task("starred-started", { status: "progress", starred: true }),
    done("starred-done", "2026-10-19T13:00:00Z", { starred: true }),
  ]);

  const view = todayView([home, work], now);

  // As a list sorts them: due ones soonest first, then the oldest.
  expect(ids(view.starred)).toEqual(["starred-overdue", "starred-today", "starred-next-week", "starred-someday", "starred-started"]);
  expect(ids(view.overdue)).toEqual(["yesterday"]);
  expect([...view.today, ...view.progress]).toEqual([]);
  expect(ids(view.done)).toEqual(["starred-done"]);
});

test("done today: finished today on this device's clock, the latest first", () => {
  const home = list("Home", [
    done("early", "2026-10-19T12:05:00Z"), // the server's time
    done("late", "2026-10-19T12:05:00.500Z"), // this device's: as text it would sort before "early"
    done("last-night", "2026-10-19T02:00:00Z"), // 10 pm on the 18th in Florida
    done("yesterday", "2026-10-18T20:00:00Z", { due_date: "2026-10-19" }), // due today, but finished: nowhere
  ]);
  const view = todayView([home], now);
  expect(ids(view.done)).toEqual(["late", "early"]);
  expect([...view.overdue, ...view.today, ...view.progress]).toEqual([]);
});

test("a time set in another zone falls on the day it is here", () => {
  const view = todayView([list("Home", [
    task("madrid", { due_date: "2026-10-20", due_time: "01:00", due_zone: "Europe/Madrid" }), // 7 pm today in Florida
    task("los-angeles", { due_date: "2026-10-19", due_time: "23:00", due_zone: "America/Los_Angeles" }), // 2 am tomorrow here
  ])], now);
  expect(ids(view.today)).toEqual(["madrid"]);
  expect(ids(view.overdue)).toEqual([]);
});

test("ticked offline, a task shows in Done today at once, and a repeating one's next is where its date puts it", () => {
  const snapshot: Snapshot = { me: "maria", lists: [list("Home", [
    task("bins", { due_date: "2026-10-19", repeat: "FREQ=WEEKLY;BYDAY=MO" }),
    task("plants", { due_date: "2026-10-18", repeat: "FREQ=DAILY" }),
  ])] };
  const queuedAt = "2026-10-19T14:00:00.000Z";
  const shown = applyQueue(snapshot, [
    { method: "PATCH", path: "/api/tasks/bins", body: { status: "done", next_id: "bins-2", finished_on: "2026-10-19" }, queuedAt },
    { method: "PATCH", path: "/api/tasks/plants", body: { status: "done", next_id: "plants-2", finished_on: "2026-10-19" }, queuedAt },
  ]);
  const view = todayView(shown.lists, now);
  expect(ids(view.done).sort()).toEqual(["bins", "plants"]);
  expect(ids(view.today)).toEqual(["plants-2"]); // every day: today's is next; the bins are next Monday
  expect(ids(view.overdue)).toEqual([]);
});
