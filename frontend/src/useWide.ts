// Desktop or phone layout: the design switches at 900px. Sizes switch in style.css at the same
// width; this is for the places where the layout itself differs (header, tabs, Focus screen).
import { useSyncExternalStore } from "react";

export const WIDE = "(min-width: 900px)"; // also in style.css

const query = matchMedia(WIDE);

export function useWide(): boolean {
  return useSyncExternalStore((changed) => {
    query.addEventListener("change", changed);
    return () => query.removeEventListener("change", changed);
  }, () => query.matches);
}
