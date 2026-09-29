// Light or dark: follows the device until someone picks one with the header's button. The choice
// is kept in localStorage; index.html applies it before the first paint, so there's no flash.
// (Logging out clears it with the rest of the site's storage: back to following the device.)
export type Theme = "light" | "dark";

const KEY = "taskly-theme"; // also in index.html
const BACKGROUND: Record<Theme, string> = { light: "#f6f6f4", dark: "#151514" }; // --bg in style.css, for the phone's status bar

export const systemDark = matchMedia("(prefers-color-scheme: dark)");

export function currentTheme(): Theme {
  const chosen = document.documentElement.dataset.theme;
  if (chosen === "light" || chosen === "dark") return chosen;
  return systemDark.matches ? "dark" : "light";
}

export function setTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", BACKGROUND[theme]);
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    // storage blocked: the choice lasts until the page is closed
  }
}
