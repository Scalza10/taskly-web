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
