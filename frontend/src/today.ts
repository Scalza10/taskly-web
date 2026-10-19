// The Today screen's tasks: from every list, what's overdue, what's due today and what's in
// progress, then what was finished today. Placed by the chips' own rules (due.ts) on this device's
// date, so a time set in another zone falls on the day it is here, and a time that has passed
// today is overdue, as its chip says.
import type { Task, TaskList } from "./api";
import { dueOf, localDay } from "./due";
import { sortTasks } from "./view";

export type Entry = { task: Task; list: TaskList };
export type Today = { overdue: Entry[]; today: Entry[]; progress: Entry[]; done: Entry[] };

export function todayView(lists: TaskList[], now: Date): Today {
  const found: Today = { overdue: [], today: [], progress: [], done: [] };
  const today = localDay(now);
  for (const list of lists) {
    for (const task of list.tasks) {
      const entry = { task, list };
      if (task.status === "done") {
        // Finished today: every change bumps updated_at (the server's, and applyQueue's offline),
        // finishing too. No "done at" is kept, so one renamed later today counts again.
        if (localDay(new Date(task.updated_at)) === today) found.done.push(entry);
        continue;
      }
      const kind = dueOf(task, now)?.kind;
      if (kind === "overdue") found.overdue.push(entry);
      else if (kind === "today") found.today.push(entry);
      else if (task.status === "progress") found.progress.push(entry);
    }
  }
  return {
    overdue: sorted(found.overdue),
    today: sorted(found.today),
    progress: sorted(found.progress),
    // The latest first. As times, not text: the server's have no milliseconds, the device's do.
    done: found.done.sort((a, b) => Date.parse(b.task.updated_at) - Date.parse(a.task.updated_at)),
  };
}

// As a list sorts (soonest due first, then the oldest), across lists.
function sorted(entries: Entry[]): Entry[] {
  const byId = new Map(entries.map((entry) => [entry.task.id, entry]));
  return sortTasks(entries.map((entry) => entry.task)).map((task) => byId.get(task.id)!);
}
