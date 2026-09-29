// Which list to show: the one this device showed last, if it still exists, else the first.
const KEY = "taskly.list";

export function pickList(lists: { id: string }[], saved: string | null): string | null {
  if (saved && lists.some((list) => list.id === saved)) return saved;
  return lists[0]?.id ?? null;
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
  try {
    localStorage.setItem(KEY, id);
  } catch {
    // not remembered; harmless
  }
}
