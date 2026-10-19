// Which list to show: the one this device showed last, if it still exists, else the first. The
// Today screen's add bar remembers its own (TODAY_KEY), falling back to the List screen's.
const KEY = "taskly.list";
const TODAY_KEY = "taskly.todayList";

// The first of the remembered ones that still exists, else the first list.
export function pickList(lists: { id: string }[], ...saved: (string | null)[]): string | null {
  return saved.find((id) => id && lists.some((list) => list.id === id)) ?? lists[0]?.id ?? null;
}

// localStorage can throw (private windows, blocked storage): then nothing is remembered.
export function savedList(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function saveList(id: string): void {
  remember(KEY, id);
}

export function savedTodayList(): string | null {
  try {
    return localStorage.getItem(TODAY_KEY);
  } catch {
    return null;
  }
}

export function saveTodayList(id: string): void {
  remember(TODAY_KEY, id);
}

function remember(key: string, id: string): void {
  try {
    localStorage.setItem(key, id);
  } catch {
    // not remembered; harmless
  }
}
