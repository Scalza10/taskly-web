import { expect, test, vi } from "vitest";
import type { Snapshot, Task } from "./api";
import type { QueuedChange } from "./store";
import { applyQueue, clearDoneChanges, statusText, syncedLabel } from "./view";

function task(id: string, created_at: string, extra: Partial<Task> = {}): Task {
  return { id, list_id: "L", title: id, status: "new", done: false, due_date: null, due_time: null, due_zone: null, notes: null, repeat: null, created_by: "tom", done_by: null, created_at, updated_at: created_at, ...extra };
}

const snapshot: Snapshot = {
  me: "maria",
  lists: [
    {
      id: "L", name: "Groceries", owner: "maria", role: "owner", members: ["maria", "tom"],
      // As the server sorts: not done first, oldest first.
      tasks: [task("eggs", "2026-09-28T09:00:00Z"), task("bread", "2026-09-28T10:00:00Z"), task("milk", "2026-09-28T08:00:00Z", { status: "done", done: true, done_by: "tom" })],
    },
  ],
};

const at = "2026-09-28T12:00:00.000Z";
const titles = (s: Snapshot) => s.lists[0].tasks.map((t) => t.title);

test("no queue shows the snapshot as it is", () => {
  expect(applyQueue(snapshot, [])).toEqual(snapshot);
});

test("a task created offline shows after the open ones, new, pending, by me", () => {
  const view = applyQueue(snapshot, [{ method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "jam" }, queuedAt: at }]);
  expect(titles(view)).toEqual(["eggs", "bread", "jam", "milk"]);
  expect(view.lists[0].tasks[2]).toMatchObject({ id: "n1", pending: true, created_by: "maria", status: "new", done: false });
});

test("ticking moves a task down and records me; unticking clears it", () => {
  const ticked = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/eggs", body: { done: true }, queuedAt: at }]);
  expect(titles(ticked)).toEqual(["bread", "milk", "eggs"]); // done ones last, oldest first
  expect(ticked.lists[0].tasks[2]).toMatchObject({ status: "done", done: true, done_by: "maria", pending: true });

  const unticked = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/milk", body: { done: false }, queuedAt: at }]);
  expect(titles(unticked)).toEqual(["milk", "eggs", "bread"]);
  expect(unticked.lists[0].tasks[0]).toMatchObject({ status: "new", done: false, done_by: null });
});

test("status moves a task through the board, as the server does", () => {
  const started = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/bread", body: { status: "progress" }, queuedAt: at }]);
  expect(started.lists[0].tasks[1]).toMatchObject({ id: "bread", status: "progress", done: false, done_by: null, pending: true });

  const finished = applyQueue(snapshot, [
    { method: "PATCH", path: "/api/tasks/bread", body: { status: "progress" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { status: "done" }, queuedAt: at },
  ]);
  expect(titles(finished)).toEqual(["eggs", "milk", "bread"]); // done ones last, oldest first
  expect(finished.lists[0].tasks.find((t) => t.id === "bread")).toMatchObject({ status: "done", done: true, done_by: "maria" });

  const reopened = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/milk", body: { status: "new" }, queuedAt: at }]);
  expect(reopened.lists[0].tasks[0]).toMatchObject({ id: "milk", status: "new", done: false, done_by: null });
});

test("done: false leaves a task in progress where it is; status wins over done", () => {
  const queue: QueuedChange[] = [
    { method: "PATCH", path: "/api/tasks/bread", body: { status: "progress" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { done: false }, queuedAt: at },
  ];
  expect(applyQueue(snapshot, queue).lists[0].tasks[1]).toMatchObject({ id: "bread", status: "progress" });
  const both = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/eggs", body: { done: true, status: "progress" }, queuedAt: at }]);
  expect(both.lists[0].tasks[0]).toMatchObject({ id: "eggs", status: "progress", done: false });
});

test("a snapshot stored before tasks had a status reads done as the status", () => {
  const old = structuredClone(snapshot);
  for (const t of old.lists[0].tasks) delete (t as Partial<Task>).status;
  expect(applyQueue(old, []).lists[0].tasks.map((t) => t.status)).toEqual(["new", "new", "done"]);
});

test("a snapshot stored before due dates has none", () => {
  const old = structuredClone(snapshot);
  for (const t of old.lists[0].tasks) {
    delete (t as Partial<Task>).due_date;
    delete (t as Partial<Task>).due_time;
    delete (t as Partial<Task>).due_zone;
  }
  const tasks = applyQueue(old, []).lists[0].tasks;
  expect(tasks.map((t) => [t.due_date, t.due_time, t.due_zone])).toEqual([[null, null, null], [null, null, null], [null, null, null]]);
});

test("due dates set, changed and removed offline, and on a task created offline", () => {
  const view = applyQueue(snapshot, [
    { method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "jam", due_date: "2026-10-17" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { due_date: "2026-10-18" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { due_date: "2026-10-18" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { due_date: null }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { status: "progress" }, queuedAt: at },
  ]);
  const due = Object.fromEntries(view.lists[0].tasks.map((t) => [t.id, t.due_date]));
  expect(due).toEqual({ n1: "2026-10-17", eggs: "2026-10-18", bread: null, milk: null });
  expect(view.lists[0].tasks.find((t) => t.id === "bread")).toMatchObject({ pending: true });
});

test("a time comes and goes with its date, as on the server", () => {
  const timed = { due_date: "2026-10-18", due_time: "15:00", due_zone: "America/New_York" };
  const view = applyQueue(snapshot, [
    { method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "dentist", ...timed }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: timed, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { title: "eggs (12)" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: timed, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { due_date: "2026-10-19" }, queuedAt: at },
  ]);
  const due = Object.fromEntries(view.lists[0].tasks.map((t) => [t.id, [t.due_date, t.due_time, t.due_zone]]));
  expect(due).toEqual({
    n1: ["2026-10-18", "15:00", "America/New_York"],
    eggs: ["2026-10-18", "15:00", "America/New_York"], // a rename leaves it alone
    bread: ["2026-10-19", null, null], // a date alone has no time
    milk: [null, null, null],
  });
});

test("a snapshot stored before notes has none", () => {
  const old = structuredClone(snapshot);
  for (const t of old.lists[0].tasks) delete (t as Partial<Task>).notes;
  expect(applyQueue(old, []).lists[0].tasks.map((t) => t.notes)).toEqual([null, null, null]);
});

test("notes set, changed and removed offline, and on a task created offline; other changes leave them", () => {
  const view = applyQueue(snapshot, [
    { method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "plumber", notes: "Call first" }, queuedAt: at },
    { method: "POST", path: "/api/tasks", body: { id: "n2", list_id: "L", title: "jam" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { notes: "A dozen" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { title: "eggs (12)", status: "progress", due_date: "2026-10-18" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { notes: "Rye" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/bread", body: { notes: null }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/milk", body: { notes: "Oat" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/milk", body: { notes: "" }, queuedAt: at },
  ]);
  const notes = Object.fromEntries(view.lists[0].tasks.map((t) => [t.id, t.notes]));
  expect(notes).toEqual({ n1: "Call first", n2: null, eggs: "A dozen", bread: null, milk: null });
  expect(view.lists[0].tasks.find((t) => t.id === "bread")).toMatchObject({ pending: true });
});

// eggs, due on a Monday and repeating every Monday at 7:30 in Madrid, with notes; added by tom.
function repeating(): Snapshot {
  const copy = structuredClone(snapshot);
  Object.assign(copy.lists[0].tasks[0], {
    due_date: "2026-10-19", due_time: "07:30", due_zone: "Europe/Madrid", notes: "Both bins", repeat: "FREQ=WEEKLY;BYDAY=MO",
  });
  return copy;
}
const finish = (id: string, next_id: string, finished_on = "2026-10-21") =>
  ({ method: "PATCH", path: `/api/tasks/${id}`, body: { status: "done", next_id, finished_on }, queuedAt: at }) as QueuedChange;
const byId = (s: Snapshot) => Object.fromEntries(s.lists[0].tasks.map((t) => [t.id, t]));

test("a snapshot stored before repeats has none", () => {
  const old = structuredClone(snapshot);
  for (const t of old.lists[0].tasks) delete (t as Partial<Task>).repeat;
  expect(applyQueue(old, []).lists[0].tasks.map((t) => t.repeat)).toEqual([null, null, null]);
});

test("finishing a repeating task offline shows the next one, which takes the repeat over", () => {
  const view = applyQueue(repeating(), [finish("eggs", "e2")]);
  const tasks = byId(view);
  expect(tasks.eggs).toMatchObject({ status: "done", repeat: null, pending: true });
  expect(tasks.e2).toMatchObject({
    list_id: "L", title: "eggs", notes: "Both bins", status: "new", done: false, done_by: null, due_date: "2026-10-26",
    due_time: "07:30", due_zone: "Europe/Madrid", repeat: "FREQ=WEEKLY;BYDAY=MO", created_by: "tom", created_at: at, pending: true,
  });
  expect(titles(view)).toEqual(["eggs", "bread", "eggs", "milk"]); // due first, the finished one with the done ones
});

test("the next one can be changed, finished and deleted offline too", () => {
  const view = applyQueue(repeating(), [
    finish("eggs", "e2"),
    { method: "PATCH", path: "/api/tasks/e2", body: { title: "eggs out" }, queuedAt: at },
    finish("e2", "e3", "2026-10-26"),
    { method: "DELETE", path: "/api/tasks/e3", queuedAt: at },
  ]);
  const tasks = byId(view);
  expect(tasks.e2).toMatchObject({ title: "eggs out", status: "done", repeat: null });
  expect(tasks.e3).toBeUndefined();
});

test("ticking twice, or unticking and ticking again, makes one next task", () => {
  const twice = applyQueue(repeating(), [finish("eggs", "e2"), finish("eggs", "e3")]);
  expect(Object.keys(byId(twice)).sort()).toEqual(["bread", "e2", "eggs", "milk"]);
  const again = applyQueue(repeating(), [
    finish("eggs", "e2"),
    { method: "PATCH", path: "/api/tasks/eggs", body: { status: "new" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { status: "done" }, queuedAt: at }, // no repeat left: nothing to name
  ]);
  const tasks = byId(again);
  expect(Object.keys(tasks).sort()).toEqual(["bread", "e2", "eggs", "milk"]); // both stay
  expect([tasks.eggs.repeat, tasks.e2.repeat]).toEqual([null, "FREQ=WEEKLY;BYDAY=MO"]);
});

test("an older page's finish drops the repeat; the server makes the next one, shown after the sync", () => {
  const view = applyQueue(repeating(), [{ method: "PATCH", path: "/api/tasks/eggs", body: { done: true }, queuedAt: at }]);
  expect(Object.keys(byId(view)).sort()).toEqual(["bread", "eggs", "milk"]);
  expect(byId(view).eggs.repeat).toBeNull();
});

test("a repeat set, changed and stopped offline; removing the due date stops it", () => {
  const view = applyQueue(repeating(), [
    { method: "PATCH", path: "/api/tasks/bread", body: { due_date: "2026-10-20", due_time: null, due_zone: null, repeat: "FREQ=DAILY" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/milk", body: { due_date: "2026-10-20", repeat: "FREQ=DAILY" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/milk", body: { repeat: null }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/eggs", body: { due_date: null }, queuedAt: at },
  ]);
  const repeats = Object.fromEntries(view.lists[0].tasks.map((t) => [t.id, t.repeat]));
  expect(repeats).toEqual({ bread: "FREQ=DAILY", milk: null, eggs: null });
});

test("tasks with a due date come first, soonest first; a date alone after that day's times", () => {
  vi.stubEnv("TZ", "America/New_York"); // this device: Florida
  try {
    const list = (tasks: Task[]): Snapshot => ({ ...snapshot, lists: [{ ...snapshot.lists[0], tasks }] });
    const shown = applyQueue(list([
      task("undated, newer", "2026-10-10T08:00:00Z"),
      task("Oct 20", "2026-10-10T09:00:00Z", { due_date: "2026-10-20" }),
      task("Sun 3 pm in Florida", "2026-10-10T10:00:00Z", { due_date: "2026-10-18", due_time: "15:00", due_zone: "America/New_York" }),
      task("Sun 6 pm in La Palma", "2026-10-10T11:00:00Z", { due_date: "2026-10-18", due_time: "18:00", due_zone: "Atlantic/Canary" }),
      task("Sunday", "2026-10-10T12:00:00Z", { due_date: "2026-10-18" }),
      task("Oct 17, done", "2026-10-10T13:00:00Z", { due_date: "2026-10-17", status: "done", done: true }),
      task("undated, oldest", "2026-10-10T07:00:00Z"),
    ]), []);
    // 6 pm in La Palma is 1 pm in Florida, so it comes before 3 pm.
    expect(titles(shown)).toEqual(["Sun 6 pm in La Palma", "Sun 3 pm in Florida", "Sunday", "Oct 20", "undated, oldest", "undated, newer", "Oct 17, done"]);
  } finally {
    vi.unstubAllEnvs();
  }
});

test("setting a due date moves a task up, as the server will", () => {
  const view = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/bread", body: { due_date: "2026-10-18" }, queuedAt: at }]);
  expect(titles(view)).toEqual(["bread", "eggs", "milk"]);
});

test("rename and delete", () => {
  const view = applyQueue(snapshot, [
    { method: "PATCH", path: "/api/tasks/eggs", body: { title: "free-range eggs" }, queuedAt: at },
    { method: "DELETE", path: "/api/tasks/bread", queuedAt: at },
  ]);
  expect(titles(view)).toEqual(["free-range eggs", "milk"]);
});

test("clear done deletes only the list's done tasks, and the screen then shows none", () => {
  const list = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/eggs", body: { status: "done" }, queuedAt: at }]).lists[0];
  const changes = clearDoneChanges(list);
  expect(changes).toEqual([
    { method: "DELETE", path: "/api/tasks/milk" },
    { method: "DELETE", path: "/api/tasks/eggs" },
  ]);
  const queue: QueuedChange[] = [
    { method: "PATCH", path: "/api/tasks/eggs", body: { status: "done" }, queuedAt: at },
    ...changes.map((change) => ({ ...change, queuedAt: at })),
  ];
  expect(titles(applyQueue(snapshot, queue))).toEqual(["bread"]);
  expect(clearDoneChanges(applyQueue(snapshot, queue).lists[0])).toEqual([]);
});

test("a task created and ticked offline shows ticked", () => {
  const queue: QueuedChange[] = [
    { method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "jam" }, queuedAt: at },
    { method: "PATCH", path: "/api/tasks/n1", body: { done: true }, queuedAt: at },
  ];
  expect(applyQueue(snapshot, queue).lists[0].tasks.find((t) => t.id === "n1")).toMatchObject({ status: "done", done: true, done_by: "maria" });
});

test("changes to tasks or lists that are gone are skipped", () => {
  const view = applyQueue(snapshot, [
    { method: "PATCH", path: "/api/tasks/gone", body: { done: true }, queuedAt: at },
    { method: "POST", path: "/api/tasks", body: { id: "n2", list_id: "deleted-list", title: "x" }, queuedAt: at },
  ]);
  expect(view).toEqual(snapshot);
});

test("the snapshot itself is never changed", () => {
  const before = JSON.stringify(snapshot);
  applyQueue(snapshot, [{ method: "DELETE", path: "/api/tasks/bread", queuedAt: at }]);
  expect(JSON.stringify(snapshot)).toBe(before);
});

test("status text", () => {
  const now = new Date("2026-09-28T12:10:00Z");
  expect(statusText("offline", 3, undefined, now)).toBe("Offline · 3 changes waiting");
  expect(statusText("offline", 0, undefined, now)).toBe("Offline");
  expect(statusText("trouble", 1, undefined, now)).toBe("Can't reach the server · 1 change waiting");
  expect(statusText("online", 2, undefined, now)).toBe("Syncing · 2 changes waiting");
  expect(statusText("online", 0, "2026-09-28T12:09:40Z", now)).toBe("Synced just now");
  expect(syncedLabel("2026-09-28T12:05:00Z", now)).toBe("Synced 5 min ago");
  expect(syncedLabel("2026-09-28T09:00:00Z", now)).toMatch(/^Synced at /);
  expect(syncedLabel(undefined, now)).toBe("Not synced yet");
});
