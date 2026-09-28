# Phase 3: Offline and Installable Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Taskly installable on phones and laptops and let people add, tick, rename and delete tasks offline, syncing when they're back online.

**Architecture:** The device keeps the last `/api/sync` answer and a queue of unsent task changes in IndexedDB (`store.ts`). What the screen shows is `applyQueue(snapshot, queue)` (`view.ts`). `sync.ts` sends the queue in order, then downloads a fresh snapshot, one sync at a time. A React hook ties them to the page and to triggers (page open, change, online, visible, every 30 s). `vite-plugin-pwa` adds the manifest and a service worker that precaches the built page. No server schema change.

**Tech Stack:** React 19 + TypeScript, `idb`, `vite-plugin-pwa` (Workbox), `@vite-pwa/assets-generator`, Vitest + `fake-indexeddb`; FastAPI for two small server changes.

**Spec:** `docs/superpowers/specs/2026-09-28-accounts-lists-offline-design.md` (sections "Sync approach", "Frontend → Phase 3: offline"). Phase **3** of 4; requires phase 2 merged.

**Branch:** `phase-3` off `main`.

## Global Constraints

- The queue holds only task changes: `POST /api/tasks`, `PATCH /api/tasks/{id}`, `DELETE /api/tasks/{id}`. List and member actions call the API directly and need a connection.
- Sync outcome per queued change: 2xx → remove; 404/409/422 → remove and add a note; 401 → stop, show login, keep the queue; network error, 429, 5xx → stop, keep the queue, retry on the next trigger. Then `GET /api/sync` and store it.
- One sync at a time; a request during a sync runs it once more afterwards.
- Triggers: page open, after each local change, `online`/`offline` events, tab becoming visible, every 30 s while visible.
- Logging in as a **different** user deletes the device's snapshot and queue first. Logging out needs a connection; it asks before discarding unsent changes; the server answers with `Clear-Site-Data: "storage"` and the page wipes its own data and reloads.
- The page never stores the password or the session token.
- The service worker never handles `/api/*`, `/health`, `/docs`, `/redoc` or `/openapi.json`.
- New task ids: `crypto.randomUUID()` (needs https or localhost).
- API compatibility from now on: a phone may send changes queued by an **older** page to a **newer** server. Add optional fields; don't rename or remove fields or endpoints the queue uses, or make them answer 4xx for what they used to accept.
- No browser dialogs (`alert`/`confirm`/`prompt`): confirmations are inline.
- Tests: `npm --prefix frontend test`; `.venv\Scripts\python.exe -m pytest`. Commits prefixed `feat:`/`fix:`/`docs:`.

## Review Focus

1. **A queued change to a task someone else deleted:** 404 → dropped with a note, and the changes after it still go through. (Task 4 test.)
2. **Someone else logs in on a device with unsent changes:** those changes are deleted before anything is sent. (Task 4 test.)
3. **The connection drops halfway through the queue:** what was sent is gone from the queue, the rest stays in order, and the next sync resumes from the right change. (Task 4 test.)
4. **A task created offline and then ticked offline:** shows ticked right away; the sync sends the create before the tick. (Task 2 and Task 4 tests.)
5. **Sync triggered again while one runs** (a change plus the 30 s timer): never two at once, and the later request isn't lost. (Task 4 test.)

---

### Task 1: Server: logout clears the device; the manifest's MIME type

**Files:**
- Modify: `taskly/auth.py`, `taskly/main.py`
- Test: `tests/test_auth.py`, `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
def test_logout_tells_the_browser_to_forget_the_device(client):
    assert client.post("/api/logout").headers["clear-site-data"] == '"storage"'
```

In `tests/test_api.py`, `test_page_and_its_files_are_served`: also write `(static / "manifest.webmanifest").write_text("{}")` and assert

```python
        assert client.get("/manifest.webmanifest").headers["content-type"].startswith("application/manifest+json")
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_auth.py tests/test_api.py -q`
Expected: 2 FAIL (`KeyError: 'clear-site-data'`; the manifest served as `application/octet-stream`).

- [ ] **Step 3: Implement**

`taskly/auth.py`, at the end of `logout`:

```python
    # The page's offline copy (IndexedDB) and its service worker. API answers are
    # no-store, so there is no HTTP cache to clear ("cache" can stall Chrome).
    response.headers["Clear-Site-Data"] = '"storage"'
```

`taskly/main.py`, next to the `.js` line:

```python
mimetypes.add_type("application/manifest+json", ".webmanifest")
```

- [ ] **Step 4: Run all Python tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add taskly/auth.py taskly/main.py tests/test_auth.py tests/test_api.py
git commit -m "feat: logout clears the device's storage; serve the web manifest"
```

---

### Task 2: What the screen shows: `applyQueue` and the status text

**Files:**
- Create: `frontend/src/view.ts`, `frontend/src/store.ts` (types only in this task)
- Modify: `frontend/src/api.ts` (`Task.pending?`)
- Test: `frontend/src/view.test.ts`

**Interfaces:**
- Produces (`store.ts`, types):
  - `type QueuedChange = { seq?: number; method: "POST" | "PATCH" | "DELETE"; path: string; body?: unknown; queuedAt: string }` (`queuedAt`: ISO time on the device, used only to sort pending tasks).
  - `type StoredSnapshot = { data: Snapshot; syncedAt: string }`.
- Produces (`api.ts`): `Task` gains `pending?: boolean` (set only by `applyQueue`).
- Produces (`view.ts`):
  - `applyQueue(snapshot: Snapshot, queue: QueuedChange[]): Snapshot`: never mutates its input.
  - `sortTasks(tasks: Task[]): Task[]`: open first, newest `created_at` first, ties keep their order.
  - `type Connection = "online" | "offline" | "trouble"`.
  - `syncedLabel(syncedAt: string | undefined, now: Date): string`, `statusText(connection: Connection, waiting: number, syncedAt: string | undefined, now: Date): string`.

- [ ] **Step 1: Types**

`frontend/src/api.ts`: add `pending?: boolean;` to `Task` with the comment `// only on this device: a change not sent yet`.

`frontend/src/store.ts` (Task 3 adds the rest of this file):

```ts
// The device's copy: the last /api/sync answer, and the task changes not sent yet, in order.
import type { Snapshot } from "./api";

// (Task 3 adds `import { openDB, type DBSchema } from "idb";` here.)

export type QueuedChange = {
  seq?: number; // set by the store; the order changes are sent in
  method: "POST" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  queuedAt: string; // device time, ISO; only sorts tasks not yet on the server
};

export type StoredSnapshot = { data: Snapshot; syncedAt: string };
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/view.test.ts`:

```ts
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `Failed to resolve import "./view"`.

- [ ] **Step 4: Write `frontend/src/view.ts`**

```ts
// What the screen shows: the last snapshot from the server with the unsent changes applied on
// top, sorted as the server sorts. Pure: easy to test, and the same answer every time.
import type { Snapshot, Task } from "./api";
import type { QueuedChange } from "./store";

const TASKS = "/api/tasks";

export type Connection = "online" | "offline" | "trouble";

export function applyQueue(snapshot: Snapshot, queue: QueuedChange[]): Snapshot {
  const lists = snapshot.lists.map((list) => ({ ...list, tasks: list.tasks.map((task) => ({ ...task })) }));
  const find = (id: string) => {
    for (const list of lists) {
      const index = list.tasks.findIndex((task) => task.id === id);
      if (index >= 0) return { list, index };
    }
    return undefined;
  };

  for (const change of queue) {
    if (change.method === "POST" && change.path === TASKS) {
      const body = change.body as { id: string; list_id: string; title: string };
      const list = lists.find((l) => l.id === body.list_id);
      if (!list || find(body.id)) continue;
      list.tasks.push({
        id: body.id, list_id: body.list_id, title: body.title, done: false,
        created_by: snapshot.me, done_by: null, created_at: change.queuedAt, updated_at: change.queuedAt, pending: true,
      });
      continue;
    }
    if (!change.path.startsWith(`${TASKS}/`)) continue;
    const found = find(change.path.slice(TASKS.length + 1));
    if (!found) continue;
    if (change.method === "DELETE") {
      found.list.tasks.splice(found.index, 1);
      continue;
    }
    const body = change.body as { title?: string; done?: boolean };
    const task = found.list.tasks[found.index];
    if (body.title !== undefined) task.title = body.title;
    if (body.done !== undefined) {
      task.done = body.done;
      task.done_by = body.done ? snapshot.me : null;
    }
    task.pending = true;
  }

  return { ...snapshot, lists: lists.map((list) => ({ ...list, tasks: sortTasks(list.tasks) })) };
}

// As the server sorts: open first, then newest first. Ties keep their order (the server's).
export function sortTasks(tasks: Task[]): Task[] {
  return tasks
    .map((task, index) => ({ task, index }))
    .sort((a, b) =>
      Number(a.task.done) - Number(b.task.done) ||
      b.task.created_at.localeCompare(a.task.created_at) ||
      a.index - b.index)
    .map(({ task }) => task);
}

export function syncedLabel(syncedAt: string | undefined, now: Date): string {
  if (!syncedAt) return "Not synced yet";
  const minutes = Math.floor((now.getTime() - new Date(syncedAt).getTime()) / 60_000);
  if (minutes < 1) return "Synced just now";
  if (minutes < 60) return `Synced ${minutes} min ago`;
  return `Synced at ${new Date(syncedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
}

export function statusText(connection: Connection, waiting: number, syncedAt: string | undefined, now: Date): string {
  const changes = waiting === 1 ? "1 change waiting" : `${waiting} changes waiting`;
  if (connection === "offline") return waiting ? `Offline · ${changes}` : "Offline";
  if (connection === "trouble") return waiting ? `Can't reach the server · ${changes}` : "Can't reach the server";
  if (waiting) return `Syncing · ${changes}`;
  return syncedLabel(syncedAt, now);
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `npm --prefix frontend test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/view.ts frontend/src/view.test.ts frontend/src/store.ts frontend/src/api.ts
git commit -m "feat: show the server's snapshot with unsent changes applied"
```

---

### Task 3: The device store (IndexedDB)

**Files:**
- Modify: `frontend/src/store.ts`
- Test: `frontend/src/store.test.ts`
- Modify: `frontend/package.json` (via npm)

**Interfaces:**
- Produces:

```ts
export interface Store {
  snapshot(): Promise<StoredSnapshot | undefined>;
  saveSnapshot(snapshot: StoredSnapshot): Promise<void>;
  queue(): Promise<QueuedChange[]>;           // oldest first, each with its seq
  enqueue(change: QueuedChange): Promise<void>; // any seq given is ignored
  dequeue(seq: number): Promise<void>;
  clear(): Promise<void>;                     // snapshot and queue
}
export function openStore(name?: string): Store;   // IndexedDB database "taskly", version 1
export function memoryStore(): Store;              // same behaviour, in memory (tests)
export async function prepareForUser(store: Store, username: string): Promise<void>;
  // keeps the device's data only if its snapshot belongs to `username` (case-insensitive); else clears it
```

- [ ] **Step 1: Install**

```powershell
npm --prefix frontend install idb
npm --prefix frontend install -D fake-indexeddb
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/store.test.ts`:

```ts
import "fake-indexeddb/auto";
import { describe, expect, test } from "vitest";
import type { Snapshot } from "./api";
import { memoryStore, openStore, prepareForUser, type Store } from "./store";

let n = 0;
const kinds: [string, () => Store][] = [
  ["memory", memoryStore],
  ["IndexedDB", () => openStore(`test-${++n}`)],
];

const snap = (me: string): Snapshot => ({ me, lists: [] });
const change = (path: string) => ({ method: "DELETE" as const, path, queuedAt: "2026-09-28T12:00:00.000Z" });

describe.each(kinds)("%s store", (_name, make) => {
  test("starts empty", async () => {
    const store = make();
    expect(await store.snapshot()).toBeUndefined();
    expect(await store.queue()).toEqual([]);
  });

  test("keeps the snapshot", async () => {
    const store = make();
    await store.saveSnapshot({ data: snap("maria"), syncedAt: "t1" });
    await store.saveSnapshot({ data: snap("maria"), syncedAt: "t2" });
    expect(await store.snapshot()).toEqual({ data: snap("maria"), syncedAt: "t2" });
  });

  test("the queue keeps its order and numbers each change", async () => {
    const store = make();
    for (const path of ["/a", "/b", "/c"]) await store.enqueue(change(path));
    const queue = await store.queue();
    expect(queue.map((c) => c.path)).toEqual(["/a", "/b", "/c"]);
    expect(queue[0].seq! < queue[1].seq! && queue[1].seq! < queue[2].seq!).toBe(true);

    await store.dequeue(queue[1].seq!);
    expect((await store.queue()).map((c) => c.path)).toEqual(["/a", "/c"]);
  });

  test("clear empties both", async () => {
    const store = make();
    await store.saveSnapshot({ data: snap("maria"), syncedAt: "t" });
    await store.enqueue(change("/a"));
    await store.clear();
    expect(await store.snapshot()).toBeUndefined();
    expect(await store.queue()).toEqual([]);
  });

  test("the same user logging in keeps the data", async () => {
    const store = make();
    await store.saveSnapshot({ data: snap("maria"), syncedAt: "t" });
    await store.enqueue(change("/a"));
    await prepareForUser(store, "Maria");
    expect(await store.queue()).toHaveLength(1);
  });

  test("another user logging in wipes it first", async () => {
    const store = make();
    await store.saveSnapshot({ data: snap("maria"), syncedAt: "t" });
    await store.enqueue(change("/a"));
    await prepareForUser(store, "tom");
    expect(await store.snapshot()).toBeUndefined();
    expect(await store.queue()).toEqual([]);
  });
});

test("the IndexedDB store survives reopening", async () => {
  const name = `test-${++n}`;
  await openStore(name).enqueue(change("/a"));
  expect((await openStore(name).queue()).map((c) => c.path)).toEqual(["/a"]);
});
```

- [ ] **Step 3: Run them to see them fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `memoryStore` is not exported.

- [ ] **Step 4: Complete `frontend/src/store.ts`**

Replace the `// (Task 3 adds …)` comment with `import { openDB, type DBSchema } from "idb";`, then append below the types:

```ts
export interface Store {
  snapshot(): Promise<StoredSnapshot | undefined>;
  saveSnapshot(snapshot: StoredSnapshot): Promise<void>;
  queue(): Promise<QueuedChange[]>;
  enqueue(change: QueuedChange): Promise<void>;
  dequeue(seq: number): Promise<void>;
  clear(): Promise<void>;
}

interface Schema extends DBSchema {
  snapshot: { key: string; value: StoredSnapshot };
  queue: { key: number; value: QueuedChange };
}

const CURRENT = "current";

export function openStore(name = "taskly"): Store {
  const db = openDB<Schema>(name, 1, {
    upgrade(database) {
      database.createObjectStore("snapshot");
      database.createObjectStore("queue", { keyPath: "seq", autoIncrement: true });
    },
  });
  return {
    async snapshot() {
      return (await db).get("snapshot", CURRENT);
    },
    async saveSnapshot(snapshot) {
      await (await db).put("snapshot", snapshot, CURRENT);
    },
    async queue() {
      return (await db).getAll("queue"); // key order, which is seq order
    },
    async enqueue(change) {
      const { seq: _ignored, ...rest } = change;
      await (await db).add("queue", rest);
    },
    async dequeue(seq) {
      await (await db).delete("queue", seq);
    },
    async clear() {
      const tx = (await db).transaction(["snapshot", "queue"], "readwrite");
      await Promise.all([tx.objectStore("snapshot").clear(), tx.objectStore("queue").clear(), tx.done]);
    },
  };
}

export function memoryStore(): Store {
  let snapshot: StoredSnapshot | undefined;
  let queue: QueuedChange[] = [];
  let next = 1;
  const copy = <T>(value: T): T => structuredClone(value);
  return {
    async snapshot() {
      return snapshot && copy(snapshot);
    },
    async saveSnapshot(value) {
      snapshot = copy(value);
    },
    async queue() {
      return copy(queue);
    },
    async enqueue(change) {
      queue.push({ ...copy(change), seq: next++ });
    },
    async dequeue(seq) {
      queue = queue.filter((c) => c.seq !== seq);
    },
    async clear() {
      snapshot = undefined;
      queue = [];
    },
  };
}

// After logging in: the device's data stays only if it is this person's.
export async function prepareForUser(store: Store, username: string): Promise<void> {
  const stored = await store.snapshot();
  if (!stored || stored.data.me.toLowerCase() !== username.toLowerCase()) await store.clear();
}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `npm --prefix frontend test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/store.ts frontend/src/store.test.ts
git commit -m "feat: keep the snapshot and unsent changes on the device"
```

---

### Task 4: Sync

**Files:**
- Create: `frontend/src/sync.ts`
- Test: `frontend/src/sync.test.ts`

**Interfaces:**
- Consumes: `Store`, `memoryStore` (tests), `Connection` (`view.ts`), `Snapshot`.
- Produces:

```ts
export type SyncState = { connection: Connection; loggedOut: boolean; notes: string[] };
export type Sync = {
  readonly state: SyncState;
  request(): Promise<void>;                        // resolves when the sync it joined (and any rerun) is done
  subscribe(listener: () => void): () => void;     // called after every sync pass
  dismissNotes(): void;
  resume(): void;                                  // after logging in again: allow syncing
};
export function createSync(store: Store, fetchFn?: typeof fetch): Sync;
```

- [ ] **Step 1: Write the failing tests**

`frontend/src/sync.test.ts`:

```ts
import { expect, test, vi } from "vitest";
import type { Snapshot } from "./api";
import { memoryStore, type QueuedChange, type Store } from "./store";
import { createSync } from "./sync";

const SNAPSHOT: Snapshot = { me: "maria", lists: [] };
const at = "2026-09-28T12:00:00.000Z";

type Answer = number | "network";

// A fake server: answers queued changes by path, and /api/sync with SNAPSHOT.
function server(answers: Record<string, Answer> = {}) {
  const calls: string[] = [];
  const fetchFn = vi.fn(async (path: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method} ${path}`;
    calls.push(key);
    const answer = answers[key] ?? 200;
    if (answer === "network") throw new TypeError("Failed to fetch");
    const body = key === "GET /api/sync" ? JSON.stringify(SNAPSHOT) : "{}";
    return new Response(answer === 204 ? null : body, { status: answer });
  });
  return { fetchFn: fetchFn as unknown as typeof fetch, calls };
}

async function queued(store: Store, ...changes: Omit<QueuedChange, "queuedAt">[]) {
  for (const change of changes) await store.enqueue({ ...change, queuedAt: at });
}

const create = { method: "POST" as const, path: "/api/tasks", body: { id: "n1", list_id: "L", title: "jam" } };
const tick = { method: "PATCH" as const, path: "/api/tasks/n1", body: { done: true } };
const remove = { method: "DELETE" as const, path: "/api/tasks/old" };

test("sends the queue in order, then stores a fresh snapshot", async () => {
  const store = memoryStore();
  await queued(store, create, tick);
  const { fetchFn, calls } = server();
  const sync = createSync(store, fetchFn);

  await sync.request();

  expect(calls).toEqual(["POST /api/tasks", "PATCH /api/tasks/n1", "GET /api/sync"]);
  expect(await store.queue()).toEqual([]);
  expect((await store.snapshot())?.data).toEqual(SNAPSHOT);
  expect(sync.state.connection).toBe("online");
});

test("sends JSON bodies", async () => {
  const store = memoryStore();
  await queued(store, tick);
  const { fetchFn } = server();
  await createSync(store, fetchFn).request();
  expect(fetchFn).toHaveBeenCalledWith("/api/tasks/n1", {
    method: "PATCH", headers: { "Content-Type": "application/json" }, body: '{"done":true}',
  });
});

test("a change to something gone is dropped with a note, and the rest still go", async () => {
  const store = memoryStore();
  await queued(store, remove, create);
  const { fetchFn, calls } = server({ "DELETE /api/tasks/old": 404 });
  const sync = createSync(store, fetchFn);

  await sync.request();

  expect(calls).toEqual(["DELETE /api/tasks/old", "POST /api/tasks", "GET /api/sync"]);
  expect(await store.queue()).toEqual([]);
  expect(sync.state.notes).toHaveLength(1);
  sync.dismissNotes();
  expect(sync.state.notes).toEqual([]);
});

test.each([409, 422])("%i is dropped with a note too", async (status) => {
  const store = memoryStore();
  await queued(store, create);
  const sync = createSync(store, server({ "POST /api/tasks": status }).fetchFn);
  await sync.request();
  expect(await store.queue()).toEqual([]);
  expect(sync.state.notes).toHaveLength(1);
});

test("losing the connection midway keeps the rest, in order, for next time", async () => {
  const store = memoryStore();
  await queued(store, create, tick, remove);
  const offline = server({ "PATCH /api/tasks/n1": "network" });
  const sync = createSync(store, offline.fetchFn);

  await sync.request();

  expect(offline.calls).toEqual(["POST /api/tasks", "PATCH /api/tasks/n1"]);
  expect((await store.queue()).map((c) => c.path)).toEqual(["/api/tasks/n1", "/api/tasks/old"]);
  expect(sync.state.connection).toBe("offline");
  expect(await store.snapshot()).toBeUndefined();
});

test.each([429, 500, 503])("%i keeps the queue and says the server is in trouble", async (status) => {
  const store = memoryStore();
  await queued(store, create);
  const sync = createSync(store, server({ "POST /api/tasks": status }).fetchFn);
  await sync.request();
  expect(await store.queue()).toHaveLength(1);
  expect(sync.state.connection).toBe("trouble");
  expect(sync.state.notes).toEqual([]);
});

test("401 stops, keeps the queue, and waits for a new login", async () => {
  const store = memoryStore();
  await queued(store, create);
  const expired = server({ "POST /api/tasks": 401 });
  const sync = createSync(store, expired.fetchFn);

  await sync.request();
  expect(sync.state.loggedOut).toBe(true);
  expect(await store.queue()).toHaveLength(1);

  await sync.request();
  expect(expired.calls).toHaveLength(1); // nothing sent while logged out

  sync.resume();
  expect(sync.state.loggedOut).toBe(false);
});

test("401 on the download also means logged out", async () => {
  const store = memoryStore();
  const sync = createSync(store, server({ "GET /api/sync": 401 }).fetchFn);
  await sync.request();
  expect(sync.state.loggedOut).toBe(true);
});

test("one sync at a time, and a request during one runs it once more", async () => {
  const store = memoryStore();
  let inFlight = 0;
  let most = 0;
  let downloads = 0;
  const fetchFn = (async () => {
    inFlight++;
    most = Math.max(most, inFlight);
    downloads++;
    await new Promise((resolve) => setTimeout(resolve, 5));
    inFlight--;
    return new Response(JSON.stringify(SNAPSHOT), { status: 200 });
  }) as unknown as typeof fetch;
  const sync = createSync(store, fetchFn);

  const first = sync.request();
  const second = sync.request();
  const third = sync.request();
  await Promise.all([first, second, third]);

  expect(most).toBe(1);
  expect(downloads).toBe(2); // the first pass, then one more for the requests made during it
});

test("listeners hear about every pass", async () => {
  const store = memoryStore();
  const sync = createSync(store, server().fetchFn);
  const listener = vi.fn();
  const unsubscribe = sync.subscribe(listener);
  await sync.request();
  unsubscribe();
  await sync.request();
  expect(listener).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run them to see them fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `Failed to resolve import "./sync"`.

- [ ] **Step 3: Write `frontend/src/sync.ts`**

```ts
// Sends the unsent changes in order, then downloads /api/sync and stores it.
// One sync at a time; asking for one while it runs makes it run once more afterwards.
import type { Snapshot } from "./api";
import type { Store } from "./store";
import type { Connection } from "./view";

export type SyncState = { connection: Connection; loggedOut: boolean; notes: string[] };

export type Sync = {
  readonly state: SyncState;
  request(): Promise<void>;
  subscribe(listener: () => void): () => void;
  dismissNotes(): void;
  resume(): void;
};

// Answers that mean "this change can never apply": drop it and tell the person.
const NOTES: Record<number, string> = {
  404: "A change couldn't be applied: the task or its list is gone.",
  409: "A change couldn't be applied: it clashed with another task.",
  422: "A change was refused by the server.",
};

export function createSync(store: Store, fetchFn: typeof fetch = (input, init) => fetch(input, init)): Sync {
  const state: SyncState = { connection: "online", loggedOut: false, notes: [] };
  const listeners = new Set<() => void>();
  let running: Promise<void> | null = null;
  let again = false;

  // undefined: the network failed.
  async function call(method: string, path: string, body?: unknown): Promise<Response | undefined> {
    try {
      return await fetchFn(path, {
        method,
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      return undefined;
    }
  }

  // Records why a sync has to stop; true when it can go on.
  function goOn(response: Response | undefined): response is Response {
    if (response === undefined) state.connection = "offline";
    else if (response.status === 401) state.loggedOut = true;
    else if (!response.ok) state.connection = "trouble";
    else return true;
    return false;
  }

  async function pass(): Promise<void> {
    if (state.loggedOut) return;
    for (const change of await store.queue()) {
      const response = await call(change.method, change.path, change.body);
      if (response && response.status in NOTES) {
        await store.dequeue(change.seq!);
        state.notes.push(NOTES[response.status]);
        continue;
      }
      if (!goOn(response)) return;
      await store.dequeue(change.seq!);
    }
    const response = await call("GET", "/api/sync");
    if (!goOn(response)) return;
    await store.saveSnapshot({ data: (await response.json()) as Snapshot, syncedAt: new Date().toISOString() });
    state.connection = "online";
  }

  function notify() {
    for (const listener of listeners) listener();
  }

  return {
    state,
    request() {
      if (running) {
        again = true;
        return running;
      }
      running = (async () => {
        try {
          do {
            again = false;
            await pass();
            notify();
          } while (again && !state.loggedOut);
        } finally {
          running = null;
        }
      })();
      return running;
    },
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    dismissNotes() {
      state.notes = [];
      notify();
    },
    resume() {
      state.loggedOut = false;
    },
  };
}
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `npm --prefix frontend test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/sync.ts frontend/src/sync.test.ts
git commit -m "feat: sync the queue, then download a fresh snapshot"
```

---

### Task 5: Installable: manifest, icons, service worker

**Files:**
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/package.json`
- Create: `frontend/public/icon.svg`, `frontend/pwa-assets.config.ts`, and the generated icons in `frontend/public/`

- [ ] **Step 1: Install**

```powershell
npm --prefix frontend install -D vite-plugin-pwa @vite-pwa/assets-generator
```

- [ ] **Step 2: The icon and its PNGs**

`frontend/public/icon.svg`:

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#3b6fd8"/>
  <path d="M136 268l84 84 160-184" fill="none" stroke="#fff" stroke-width="48" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
```

`frontend/pwa-assets.config.ts`:

```ts
import { defineConfig, minimal2023Preset } from "@vite-pwa/assets-generator/config";

// npm run icons: makes the PNG icons and favicon in public/ from icon.svg. Run it when the icon changes.
export default defineConfig({ preset: minimal2023Preset, images: ["public/icon.svg"] });
```

In `frontend/package.json` scripts add `"icons": "pwa-assets-generator"`, then run:

```powershell
npm --prefix frontend run icons
```

Expected: `public/` gains `pwa-64x64.png`, `pwa-192x192.png`, `pwa-512x512.png`, `maskable-icon-512x512.png`, `apple-touch-icon-180x180.png`, `favicon.ico`.

- [ ] **Step 3: The plugin**

`frontend/vite.config.ts`: `import { VitePWA } from "vite-plugin-pwa";` and set `plugins` to:

```ts
  plugins: [
    react(),
    VitePWA({
      // A new deploy's page takes over the next time the app is opened.
      registerType: "autoUpdate",
      includeAssets: ["favicon.ico", "apple-touch-icon-180x180.png", "icon.svg"],
      manifest: {
        name: "Taskly",
        short_name: "Taskly",
        description: "Shared to-do lists",
        start_url: "/",
        display: "standalone",
        theme_color: "#f6f6f4",
        background_color: "#f6f6f4",
        icons: [
          { src: "pwa-192x192.png", sizes: "192x192", type: "image/png" },
          { src: "pwa-512x512.png", sizes: "512x512", type: "image/png" },
          { src: "maskable-icon-512x512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      workbox: {
        // The page handles data itself (store.ts, sync.ts); the service worker only serves the page's files.
        navigateFallbackDenylist: [/^\/api\//, /^\/health$/, /^\/docs/, /^\/redoc/, /^\/openapi\.json$/],
      },
    }),
  ],
```

`frontend/tsconfig.json`: `"types": ["vite/client", "vite-plugin-pwa/client"]`.

`frontend/src/main.tsx`, add:

```tsx
import { registerSW } from "virtual:pwa-register";

registerSW({ immediate: true });
```

`frontend/index.html`, in `<head>` after the viewport meta:

```html
  <meta name="theme-color" content="#f6f6f4">
  <link rel="icon" href="/favicon.ico" sizes="48x48">
  <link rel="icon" href="/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon-180x180.png">
```

- [ ] **Step 4: Build and check the output**

Run: `npm --prefix frontend run build`
Expected: the output lists `sw.js`, `workbox-*.js`, `manifest.webmanifest`, and "PWA … precache N entries". Then:

```powershell
Select-String -Path taskly/static/index.html -Pattern 'rel="manifest"'
```

Expected: one match.

- [ ] **Step 5: Check it in the browser**

Start uvicorn only (port 8000 serves the build) and open <http://localhost:8000/> in Chrome:
- DevTools → Application → Manifest: name Taskly, icons shown, no errors; the address bar offers "Install".
- Application → Service workers: `sw.js` activated and running.
- Network → Offline, reload: the page still loads (the data part comes in Task 6).

- [ ] **Step 6: Commit**

```bash
git add frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/src/main.tsx frontend/package.json frontend/package-lock.json frontend/pwa-assets.config.ts frontend/public
git commit -m "feat: installable, with a service worker for the page's files"
```

---

### Task 6: The page works from the device's copy

**Files:**
- Create: `frontend/src/device.ts`, `frontend/src/useLocal.ts`, `frontend/src/StatusLine.tsx`
- Modify: `frontend/src/App.tsx`, `frontend/src/ListsPage.tsx`, `frontend/src/Tasks.tsx`, `frontend/src/TaskItem.tsx`, `frontend/src/ListPicker.tsx`, `frontend/src/AccountBar.tsx`, `frontend/src/style.css`

**Interfaces:**
- Consumes: `openStore`, `prepareForUser`, `createSync`, `applyQueue`, `statusText`.
- Produces (`device.ts`): `store: Store`, `sync: Sync` (one of each per page load), `forgetDevice(): Promise<void>`.
- Produces (`useLocal.ts`): `type Local = { stored: StoredSnapshot | undefined; queue: QueuedChange[]; sync: SyncState }`, `type Enqueue = (change: { method: QueuedChange["method"]; path: string; body?: unknown }) => Promise<void>`, `useLocal(): { local: Local | null; enqueue: Enqueue }`.
- `ListsPage({ onSessionLost })`: `onSessionLost` shows the login screen and keeps the device's data. `AccountBar` logs out by itself and reloads the page.

- [ ] **Step 1: `device.ts` and the hook**

`frontend/src/device.ts`:

```ts
// This device's store and sync, one of each per page load.
import { openStore } from "./store";
import { createSync } from "./sync";

export const store = openStore();
export const sync = createSync(store);

// After logging out: nothing of this person stays on the device. The server's Clear-Site-Data
// may already have closed the database, so failures here are fine; the page reloads next.
export async function forgetDevice(): Promise<void> {
  try {
    await store.clear();
  } catch {
    // already cleared by Clear-Site-Data
  }
  try {
    for (const key of await caches.keys()) await caches.delete(key);
  } catch {
    // no Cache API (plain http on another host): nothing cached
  }
}
```

`frontend/src/useLocal.ts`:

```ts
// The device's copy for React: reloads after every sync pass and every local change,
// and asks for a sync on page open, after changes, when back online, when visible, and every 30 s.
import { useCallback, useEffect, useState } from "react";
import { store, sync } from "./device";
import type { QueuedChange, StoredSnapshot } from "./store";
import type { SyncState } from "./sync";

export type Local = { stored: StoredSnapshot | undefined; queue: QueuedChange[]; sync: SyncState };
export type Enqueue = (change: { method: QueuedChange["method"]; path: string; body?: unknown }) => Promise<void>;

const EVERY = 30_000;

export function useLocal(): { local: Local | null; enqueue: Enqueue } {
  const [local, setLocal] = useState<Local | null>(null);

  const reload = useCallback(async () => {
    const [stored, queue] = await Promise.all([store.snapshot(), store.queue()]);
    setLocal({ stored, queue, sync: { ...sync.state, notes: [...sync.state.notes] } });
  }, []);

  useEffect(() => {
    const unsubscribe = sync.subscribe(() => void reload());
    const poke = () => {
      if (document.visibilityState === "visible") void sync.request();
    };
    void reload().then(() => sync.request());
    window.addEventListener("online", poke);
    window.addEventListener("offline", poke);
    document.addEventListener("visibilitychange", poke);
    const timer = window.setInterval(poke, EVERY);
    return () => {
      unsubscribe();
      window.removeEventListener("online", poke);
      window.removeEventListener("offline", poke);
      document.removeEventListener("visibilitychange", poke);
      window.clearInterval(timer);
    };
  }, [reload]);

  const enqueue = useCallback<Enqueue>(async (change) => {
    await store.enqueue({ ...change, queuedAt: new Date().toISOString() });
    await reload();
    void sync.request();
  }, [reload]);

  return { local, enqueue };
}
```

`frontend/src/StatusLine.tsx`:

```tsx
// "Offline · 3 changes waiting", "Synced 2 min ago", and notes about changes that couldn't apply.
import { useEffect, useState } from "react";
import { sync } from "./device";
import type { Local } from "./useLocal";
import { statusText } from "./view";

export function StatusLine({ local }: { local: Local }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const { connection, notes } = local.sync;
  return (
    <div className={`status ${connection}`} role="status">
      <span>{statusText(connection, local.queue.length, local.stored?.syncedAt, now)}</span>
      {notes.length > 0 && (
        <span className="error">
          {notes.length === 1 ? notes[0] : `${notes.length} changes couldn't be applied.`}{" "}
          <button type="button" className="plain" onClick={() => sync.dismissNotes()}>OK</button>
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Task changes go through the queue**

`frontend/src/Tasks.tsx`: replace the `change: Change` prop with `enqueue: Enqueue` (from `./useLocal`) and the add request with:

```tsx
    await enqueue({ method: "POST", path: "/api/tasks", body: { id: crypto.randomUUID(), list_id: list.id, title: trimmed } });
```

and pass `enqueue={enqueue}` to each `TaskItem`.

`frontend/src/TaskItem.tsx`: replace the `change: Change` prop with `enqueue: Enqueue`, and the three requests with:

```tsx
// tick
void enqueue({ method: "PATCH", path, body: { done } });
// rename (in onBlur)
if (newTitle && newTitle !== task.title) void enqueue({ method: "PATCH", path, body: { title: newTitle } });
// delete
onClick={() => void enqueue({ method: "DELETE", path })}
```

and give the `<li>` the class `pending` when `task.pending`:

```tsx
    <li className={[task.done && "done", task.pending && "pending"].filter(Boolean).join(" ") || undefined}>
```

- [ ] **Step 3: `ListsPage` reads the device's copy**

Replace `frontend/src/ListsPage.tsx`:

```tsx
// The lists, from the device's copy (works offline). Task changes queue up and sync;
// list and member changes go straight to the server and need a connection.
import { useEffect, useState } from "react";
import { ApiError } from "./api";
import { sync } from "./device";
import { ListPicker } from "./ListPicker";
import { ListSettings } from "./ListSettings";
import { isLoggedOut } from "./messages";
import { NewList } from "./NewList";
import { pickList, savedList, saveList } from "./pickList";
import { StatusLine } from "./StatusLine";
import { Tasks } from "./Tasks";
import { useLocal } from "./useLocal";
import { applyQueue } from "./view";

export type Change = <T>(request: () => Promise<T>) => Promise<T | undefined>;
type Panel = "none" | "new" | "settings";

export function ListsPage({ onSessionLost }: { onSessionLost: () => void }) {
  const { local, enqueue } = useLocal();
  const [selected, setSelected] = useState<string | null>(savedList);
  const [panel, setPanel] = useState<Panel>("none");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (local?.sync.loggedOut) onSessionLost();
  }, [local, onSessionLost]);

  async function change<T>(request: () => Promise<T>): Promise<T | undefined> {
    let result: T | undefined;
    try {
      result = await request();
      setError(null);
    } catch (e) {
      if (isLoggedOut(e)) {
        onSessionLost();
        return undefined;
      }
      setError(e instanceof ApiError ? e.message : "That needs a connection.");
    }
    await sync.request();
    return result;
  }

  function choose(id: string) {
    setSelected(id);
    saveList(id);
    setPanel("none");
  }

  if (!local) return null;
  if (!local.stored) {
    return (
      <main>
        <h1>Taskly</h1>
        <StatusLine local={local} />
      </main>
    );
  }

  const view = applyQueue(local.stored.data, local.queue);
  const current = view.lists.find((list) => list.id === pickList(view.lists, selected));
  const online = local.sync.connection === "online";
  const toggle = (which: Panel) => setPanel(panel === which ? "none" : which);

  return (
    <main>
      <ListPicker
        lists={view.lists}
        current={current}
        online={online}
        onChoose={choose}
        onNew={() => toggle("new")}
        onSettings={() => toggle("settings")}
      />
      {online && panel === "new" && <NewList change={change} onCreated={choose} onCancel={() => setPanel("none")} />}
      {online && panel === "settings" && current && (
        <ListSettings list={current} me={view.me} change={change} onClose={() => setPanel("none")} />
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {current ? (
        <Tasks key={current.id} list={current} enqueue={enqueue} />
      ) : (
        <p className="empty">No lists yet. Make one with “New list”.</p>
      )}
      <StatusLine local={local} />
    </main>
  );
}
```

`frontend/src/ListPicker.tsx`: add an `online: boolean` prop; on both buttons set `disabled={!online}` and `title={online ? undefined : "Needs a connection"}`.

- [ ] **Step 4: Logging in and out with a device copy**

Replace `frontend/src/App.tsx`:

```tsx
// Which screen: the lists (from the device's copy if there is one, so it opens offline),
// the login screen, or "connect once" for a first visit without a connection.
import { useCallback, useEffect, useState } from "react";
import { api, type Me } from "./api";
import { AccountBar } from "./AccountBar";
import { store, sync } from "./device";
import { ListsPage } from "./ListsPage";
import { Login } from "./Login";
import { isLoggedOut } from "./messages";
import { prepareForUser } from "./store";

type Screen = { kind: "checking" } | { kind: "login" } | { kind: "connect" } | { kind: "lists"; me: string };

export function App() {
  const [screen, setScreen] = useState<Screen>({ kind: "checking" });

  useEffect(() => {
    void (async () => {
      const stored = await store.snapshot();
      if (stored) return setScreen({ kind: "lists", me: stored.data.me });
      try {
        const me = await api<Me>("GET", "/api/me");
        await prepareForUser(store, me.username);
        setScreen({ kind: "lists", me: me.username });
      } catch (e) {
        setScreen(isLoggedOut(e) ? { kind: "login" } : { kind: "connect" });
      }
    })();
  }, []);

  // The session ended (expired, password changed elsewhere): log in again, keep unsent changes.
  const sessionLost = useCallback(() => setScreen({ kind: "login" }), []);

  async function loggedIn(username: string) {
    await prepareForUser(store, username); // someone else's unsent changes are deleted, never sent
    sync.resume();
    setScreen({ kind: "lists", me: username });
  }

  switch (screen.kind) {
    case "checking":
      return null;
    case "connect":
      return <main><h1>Taskly</h1><p className="hint">Connect to the internet once to log in.</p></main>;
    case "login":
      return <Login onLoggedIn={loggedIn} />;
    case "lists":
      return (
        <>
          <AccountBar username={screen.me} />
          <ListsPage onSessionLost={sessionLost} />
        </>
      );
  }
}
```

Replace `logout` and the start of `AccountBar` in `frontend/src/AccountBar.tsx`:

```tsx
// Who is logged in, with "Change password" and "Log out". Logging out needs a connection:
// only the server can end the session. Unsent changes are sent first, or discarded on request.
import { useState } from "react";
import { api } from "./api";
import { ChangePassword } from "./ChangePassword";
import { forgetDevice, store, sync } from "./device";

export function AccountBar({ username }: { username: string }) {
  const [changing, setChanging] = useState(false);
  const [unsynced, setUnsynced] = useState(0);
  const [error, setError] = useState<string | null>(null);

  async function logout() {
    if ((await store.queue()).length) {
      await sync.request();
      const waiting = (await store.queue()).length;
      if (waiting) return setUnsynced(waiting);
    }
    await logoutAnyway();
  }

  async function logoutAnyway() {
    try {
      await api("POST", "/api/logout");
    } catch {
      setUnsynced(0);
      return setError("Logging out needs a connection.");
    }
    await forgetDevice();
    location.reload(); // a fresh page: new store, login screen
  }
```

and in its JSX, after the `{error && …}` line:

```tsx
      {unsynced > 0 && (
        <div className="panel row confirm">
          <span>{unsynced === 1 ? "1 change hasn't" : `${unsynced} changes haven't`} synced. Log out anyway?</span>
          <button type="button" className="danger" onClick={logoutAnyway}>Log out</button>
          <button type="button" className="plain" onClick={() => setUnsynced(0)}>Cancel</button>
        </div>
      )}
```

(`onLoggedOut` is no longer a prop.)

`frontend/src/style.css`, append:

```css
/* A change not sent to the server yet. */
li.pending { border-style: dashed; }

.status { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-top: 24px; color: var(--muted); font-size: 13px; }
.status.offline, .status.trouble { color: var(--text); }
```

- [ ] **Step 5: Typecheck, test, build**

Run: `npm --prefix frontend run build` and `npm --prefix frontend test`
Expected: no type errors; all tests pass. Fix any leftover references to `onLoggedOut`/`change` props the compiler reports in `TaskItem`/`Tasks`.

- [ ] **Step 6: Check it in the browser, like a user**

`npm --prefix frontend run build`, then uvicorn alone on <http://localhost:8000/> (the service worker only runs on the build). In Chrome:
- Log in: lists show; status "Synced just now".
- DevTools → Network → **Offline**. Add "jam" (dashed border), tick "bread", rename "eggs", delete one. Status: "Offline · 4 changes waiting". New list and Settings are greyed out with "Needs a connection".
- Reload while still offline: the page opens, with the same four changes shown.
- Back **Online**: within a moment (or on the next click) the status goes "Synced just now", dashed borders go. In another browser logged in as someone in the list, the changes appear within 30 s.
- Offline again; in the other browser, delete a task; here, tick that same task; go online: the note "A change couldn't be applied: the task or its list is gone." with OK; the task is gone.
- Log out with a change waiting and the server stopped: "Logging out needs a connection." Start the server, queue a change offline, go online and log out: it syncs and logs out, and the page reloads to the login screen. DevTools → Application → IndexedDB `taskly`: empty.
- Log in as a different user on the same browser after queuing a change offline as the first user (log in via the session-expired path: delete the `taskly_session` cookie, go online): the first user's queued change is not sent (check the Network tab), and the second user's lists show.
- Phone width; console: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat: the page works offline from the device's copy and syncs"
```

---

### Task 7: README and CLAUDE.md

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: README, a new section "## On your phone" (after "## Accounts")**

```markdown
## On your phone

Open `https://<site>/`, log in, then install it:

- **iPhone (Safari):** Share → **Add to Home Screen**. Do this: Safari deletes a
  website's saved data after 7 days without a visit, but not an installed app's,
  and unsent changes live there.
- **Android (Chrome):** menu → **Install app** (or "Add to Home screen").
- **Laptop (Chrome or Edge):** the install icon at the end of the address bar.

**Offline** you can see your lists and add, tick, rename and delete tasks. The
line at the bottom says how many changes are waiting; they're sent when you're
back online and the app is open (it doesn't sync in the background). Creating
lists, settings and logging out need a connection. If someone deleted a task you
changed offline, your change is dropped and the app says so.

**Logging out** removes everything Taskly saved on the device. If changes
haven't synced yet, it asks first. Someone else logging in on the same device
never sees or sends your unsent changes.

**Checking a new version on a phone:** after a deploy, close and reopen the app
(it updates on open). Then: go offline (airplane mode), tick a task, add one,
reopen the app (still there, "2 changes waiting"), go online, and check another
device shows the changes.
```

- [ ] **Step 2: README, "Run it locally"**

Add at the end of that section:

```markdown
The service worker (offline and install) only runs on the build: use
`npm --prefix frontend run build` and uvicorn's <http://localhost:8000/> to try
them, with DevTools → Network → Offline. Opening the dev server from a phone on
your network (`http://<pc-ip>:5173`) doesn't work: adding tasks needs
`crypto.randomUUID()`, which browsers only offer on https or localhost.
```

- [ ] **Step 3: CLAUDE.md**

In "## Architecture", replace the **Frontend** bullet's sentence "After every change the page reloads `/api/sync`" with:

```markdown
The page draws from the device's copy: `store.ts` (IndexedDB: the last `/api/sync` answer and a queue of unsent task changes), `view.ts` (`applyQueue`: pure, what the screen shows), `sync.ts` (sends the queue in order, then downloads `/api/sync`; one at a time). Task changes go into the queue, then the page redraws from the local copy and syncs; list and member changes call the API directly and need a connection. `device.ts` holds the page's one `store` and `sync`. `vite-plugin-pwa` makes the manifest and service worker (it never handles `/api`). No `alert`/`confirm`: confirmations are inline.
```

Add a new bullet under **Lists**:

```markdown
- **Old pages talk to new servers.** A phone can come online with changes queued by an older version of the page and send them before it loads the new one. Keep `POST/PATCH/DELETE /api/tasks` accepting what they accept today: add optional fields; don't rename or remove fields or endpoints the queue uses. A change the server can't apply must answer 404, 409 or 422 (the page drops it with a note), never 5xx (the page would retry it forever).
```

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: installing on a phone, offline, and API compatibility for queued changes"
```

---

### Task 8: Deploy phase 3

- [ ] **Step 1:** Merge `phase-3` into `main`; both test suites pass on `main`.
- [ ] **Step 2:** `.\scripts\deploy.ps1`. Expected: `schema 3, nothing to do`, `Deployed. status=ok`.
- [ ] **Step 3:** With the user, on a real iPhone and an Android phone: install from the browser and run the README's "Checking a new version on a phone" steps. Report anything iPhone-specific (the spec's known risk).
