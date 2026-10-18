// Search: the tasks of every list whose title and notes have all the words typed between them, in
// any order, ignoring case and accents. Runs on the device's copy, so it works offline. Each list's
// tasks keep the screen's order (not done first), and lists keep theirs; lists without a match are left out.
import type { Task, TaskList } from "./api";

export type Found = { list: TaskList; tasks: Task[] };

function fold(text: string): string {
  return text.normalize("NFD").replace(/\p{M}/gu, "").toLocaleLowerCase();
}

export function searchTasks(lists: TaskList[], query: string): Found[] {
  const words = fold(query).split(/\s+/).filter(Boolean);
  if (words.length === 0) return [];
  return lists
    .map((list) => ({ list, tasks: list.tasks.filter((task) => {
      const text = fold(`${task.title}\n${task.notes ?? ""}`);
      return words.every((word) => text.includes(word));
    }) }))
    .filter((found) => found.tasks.length > 0);
}
