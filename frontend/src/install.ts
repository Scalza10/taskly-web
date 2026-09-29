// "Download": installing the page as an app, so it opens from the home screen and works offline.
// Chrome, Edge and Android hand the page an install prompt (beforeinstallprompt); Safari and
// Firefox don't, so the page shows the steps instead. watchInstall runs before React mounts:
// the prompt can arrive before the header is drawn.
import { useSyncExternalStore } from "react";

type InstallPrompt = Event & { prompt(): Promise<void> };
export type InstallState = "installed" | "prompt" | "steps";

let deferred: InstallPrompt | null = null;
let installed = false;
const listeners = new Set<() => void>();
const changed = () => listeners.forEach((listener) => listener());

export function watchInstall() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // no mini-infobar: the header has the button
    deferred = event as InstallPrompt;
    changed();
  });
  window.addEventListener("appinstalled", () => {
    installed = true;
    deferred = null;
    changed();
  });
}

function state(): InstallState {
  const standalone = matchMedia("(display-mode: standalone)").matches || (navigator as { standalone?: boolean }).standalone === true;
  if (installed || standalone) return "installed";
  return deferred ? "prompt" : "steps";
}

export function useInstall(): InstallState {
  return useSyncExternalStore((listener) => {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }, state);
}

// A prompt can be shown once; if it's dismissed, the browser may offer a new one later.
export async function promptInstall() {
  const event = deferred;
  deferred = null;
  changed();
  await event?.prompt();
}
