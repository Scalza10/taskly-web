// Which screen the tabs show: List, Board or Focus. Kept on this device, like the chosen list.
export type Screen = "list" | "board" | "focus";

const KEY = "taskly.screen";
export const SCREENS: { screen: Screen; label: string }[] = [
  { screen: "list", label: "List" },
  { screen: "board", label: "Board" },
  { screen: "focus", label: "Focus" },
];

export function savedScreen(): Screen {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "list" || saved === "board" || saved === "focus") return saved;
  } catch {
    // storage blocked
  }
  return "list";
}

export function saveScreen(screen: Screen): void {
  try {
    localStorage.setItem(KEY, screen);
  } catch {
    // not remembered; harmless
  }
}
