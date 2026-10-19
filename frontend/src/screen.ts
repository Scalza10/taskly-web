// Which screen the tabs show: Today (every list), List, Board or Focus (the chosen list). Kept on
// this device, like the chosen list; a new one starts on List.
export type Screen = "today" | "list" | "board" | "focus";

const KEY = "taskly.screen";
export const SCREENS: { screen: Screen; label: string }[] = [
  { screen: "today", label: "Today" },
  { screen: "list", label: "List" },
  { screen: "board", label: "Board" },
  { screen: "focus", label: "Focus" },
];

export function savedScreen(): Screen {
  try {
    const saved = localStorage.getItem(KEY);
    if (SCREENS.some((s) => s.screen === saved)) return saved as Screen;
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
