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
