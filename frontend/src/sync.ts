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
            try {
              await pass();
            } catch {
              // If the device fails (store or response.json), report trouble and keep going.
              // notify() still runs so listeners hear about it and request() always resolves.
              state.connection = "trouble";
            }
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
