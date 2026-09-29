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
