import { expect, test } from "vitest";
import type { Snapshot, Task } from "./api";
import type { QueuedChange } from "./store";
import { applyQueue, statusText, syncedLabel } from "./view";

function task(id: string, created_at: string, extra: Partial<Task> = {}): Task {
  return { id, list_id: "L", title: id, done: false, created_by: "tom", done_by: null, created_at, updated_at: created_at, ...extra };
}

const snapshot: Snapshot = {
  me: "maria",
  lists: [
    {
      id: "L", name: "Groceries", owner: "maria", role: "owner", members: ["maria", "tom"],
      tasks: [task("bread", "2026-09-28T10:00:00Z"), task("eggs", "2026-09-28T09:00:00Z"), task("milk", "2026-09-28T08:00:00Z", { done: true, done_by: "tom" })],
    },
  ],
};

const at = "2026-09-28T12:00:00.000Z";
const titles = (s: Snapshot) => s.lists[0].tasks.map((t) => t.title);

test("no queue shows the snapshot as it is", () => {
  expect(applyQueue(snapshot, [])).toEqual(snapshot);
});

test("a task created offline shows first, pending, by me", () => {
  const view = applyQueue(snapshot, [{ method: "POST", path: "/api/tasks", body: { id: "n1", list_id: "L", title: "jam" }, queuedAt: at }]);
  expect(titles(view)).toEqual(["jam", "bread", "eggs", "milk"]);
  expect(view.lists[0].tasks[0]).toMatchObject({ id: "n1", pending: true, created_by: "maria", done: false });
});

test("ticking moves a task down and records me; unticking clears it", () => {
  const ticked = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/bread", body: { done: true }, queuedAt: at }]);
  expect(titles(ticked)).toEqual(["eggs", "bread", "milk"]);
  expect(ticked.lists[0].tasks[1]).toMatchObject({ done: true, done_by: "maria", pending: true });

  const unticked = applyQueue(snapshot, [{ method: "PATCH", path: "/api/tasks/milk", body: { done: false }, queuedAt: at }]);
  expect(titles(unticked)).toEqual(["bread", "eggs", "milk"]);
  expect(unticked.lists[0].tasks[2].done_by).toBeNull();
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
  expect(applyQueue(snapshot, queue).lists[0].tasks.find((t) => t.id === "n1")).toMatchObject({ done: true, done_by: "maria" });
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
