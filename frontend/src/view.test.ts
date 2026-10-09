import { expect, test } from "vitest";
import type { Snapshot, Task } from "./api";
import type { QueuedChange } from "./store";
import { applyQueue, statusText, syncedLabel } from "./view";

function task(id: string, created_at: string, extra: Partial<Task> = {}): Task {
  return { id, list_id: "L", title: id, status: "new", done: false, created_by: "tom", done_by: null, created_at, updated_at: created_at, ...extra };
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

test("rename and delete", () => {
  const view = applyQueue(snapshot, [
    { method: "PATCH", path: "/api/tasks/eggs", body: { title: "free-range eggs" }, queuedAt: at },
    { method: "DELETE", path: "/api/tasks/bread", queuedAt: at },
  ]);
  expect(titles(view)).toEqual(["free-range eggs", "milk"]);
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
