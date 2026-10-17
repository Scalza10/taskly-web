// Due dates: a calendar day ("2026-10-17", no time or zone) as the server stores it, compared with
// this device's own date. The chips on the List and the Board, and the List's "Due today" filter.
import type { Task } from "./api";

// overdue: before today and not done. date: any other day (a done task is never overdue).
export type DueKind = "overdue" | "today" | "tomorrow" | "date";
export type Due = { kind: DueKind; label: string; full: string };

const pad = (n: number) => String(n).padStart(2, "0");

// The device's date as a calendar day.
export function localDay(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Local midnight of a calendar day, so formatting it never shows the day before.
// setFullYear: new Date(y, m, d) would read years below 100 as 19xx.
function toDate(day: string): Date {
  const [year, month, date] = day.split("-").map(Number);
  const result = new Date(0);
  result.setFullYear(year, month - 1, date);
  result.setHours(0, 0, 0, 0);
  return result;
}

export function addDays(day: string, days: number): string {
  const date = toDate(day);
  date.setDate(date.getDate() + days);
  return localDay(date);
}

// "Today", "Tomorrow", "Overdue · Oct 15", "Wed, Oct 21" (the coming week), "Nov 30", "Jan 5, 2027";
// full is the whole date, for a tooltip. undefined: no due date.
export function dueOf(task: Pick<Task, "due_date" | "status">, today: string, locale?: string): Due | undefined {
  const day = task.due_date;
  if (!day) return undefined;
  const date = toDate(day);
  const full = date.toLocaleDateString(locale, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  if (day === today) return { kind: "today", label: "Today", full };
  if (day === addDays(today, 1)) return { kind: "tomorrow", label: "Tomorrow", full };
  const options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  if (day.slice(0, 4) !== today.slice(0, 4)) options.year = "numeric";
  if (day > today && day < addDays(today, 7)) options.weekday = "short";
  const label = date.toLocaleDateString(locale, options);
  if (day < today && task.status !== "done") return { kind: "overdue", label: `Overdue · ${label}`, full };
  return { kind: "date", label, full };
}

// The "Due today" filter: the open tasks due today, and the overdue ones (still to do today).
export function dueToday(tasks: Task[], today: string): Task[] {
  return tasks.filter((task) => task.status !== "done" && !!task.due_date && task.due_date <= today);
}
