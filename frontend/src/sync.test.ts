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
    signal: expect.any(AbortSignal),
  });
});

test("a request that hangs times out like a lost connection and keeps the queue", async () => {
  const store = memoryStore();
  await queued(store, tick);
  const hangs = ((_path: RequestInfo | URL, init?: RequestInit) =>
    new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(init.signal!.reason));
    })) as unknown as typeof fetch;
  const sync = createSync(store, hangs, 10);

  await sync.request();

  expect(sync.state.connection).toBe("offline");
  expect(await store.queue()).toHaveLength(1);
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

  const working = server();
  await createSync(store, working.fetchFn).request();
  expect(working.calls).toEqual(["PATCH /api/tasks/n1", "DELETE /api/tasks/old", "GET /api/sync"]);
  expect(await store.queue()).toEqual([]);
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

test("a store failure resolves with trouble and notifies listeners", async () => {
  const store = { ...memoryStore(), queue: () => Promise.reject(new Error("IndexedDB lost")) };
  const sync = createSync(store, server().fetchFn);
  const listener = vi.fn();
  sync.subscribe(listener);

  await sync.request();

  expect(sync.state.connection).toBe("trouble");
  expect(listener).toHaveBeenCalledTimes(1);
});
