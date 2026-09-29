// This device's store and sync, one of each per page load.
import { openStore } from "./store";
import { createSync } from "./sync";

// Another window's logout wipes the database under this one: reload to the login screen.
export const store = openStore("taskly", { onTerminated: () => location.reload() });
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
  try {
    // Some browsers (Safari < 17) keep the worker after Clear-Site-Data, now with an empty
    // precache; the reload registers a fresh one.
    for (const registration of await navigator.serviceWorker.getRegistrations()) await registration.unregister();
  } catch {
    // no service worker support
  }
}
