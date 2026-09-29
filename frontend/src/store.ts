// The device's copy: the last /api/sync answer, and the task changes not sent yet, in order.
import type { Snapshot } from "./api";
import { openDB, type DBSchema } from "idb";

export type QueuedChange = {
  seq?: number; // set by the store; the order changes are sent in
  method: "POST" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  queuedAt: string; // device time, ISO; only sorts tasks not yet on the server
};

export type StoredSnapshot = { data: Snapshot; syncedAt: string };

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
