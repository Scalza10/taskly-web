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
