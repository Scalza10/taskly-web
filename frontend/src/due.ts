// Due dates: a calendar day ("2026-10-17", no time or zone) as the server stores it, compared with
// this device's own date. A task can also have a time ("15:00") in the time zone it was set in
// (due_zone, like "America/New_York"): one moment for everyone, shown in this device's own time,
// so a 3 pm appointment set in Florida reads 8 pm in the Canaries. The chips on the List and the
// Board, the List's picker and its "Due today" filter.
import type { Task } from "./api";

// overdue: before today (with a time: before now) and not done. date: any other day (a done task
// is never overdue). note: the time where it was set, when that reads differently here.
export type DueKind = "overdue" | "today" | "tomorrow" | "date";
export type Due = { kind: DueKind; label: string; full: string; note?: string };
// A due date as this device's pickers show it, and how it repeats from it (see repeat.ts).
export type DueInput = { date: string; time: string | null; repeat: string | null };

type DueFields = Pick<Task, "due_date" | "due_time" | "due_zone" | "status">;

const pad = (n: number) => String(n).padStart(2, "0");

// The device's date as a calendar day.
export function localDay(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function localClock(date: Date): string {
  return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function deviceZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
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

// A clock reading as if it were UTC, in ms.
function asUtc(year: number, month: number, date: number, hour: number, minute: number, second = 0): number {
  const clock = new Date(0);
  clock.setUTCFullYear(year, month - 1, date);
  clock.setUTCHours(hour, minute, second, 0);
  return clock.getTime();
}

// How far a zone's clocks are ahead of UTC at a moment, in ms.
function offset(at: number, zone: string): number {
  const parts: Record<string, string> = {};
  const format = new Intl.DateTimeFormat("en-US", {
    timeZone: zone, hourCycle: "h23", year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "numeric", second: "numeric",
  });
  for (const part of format.formatToParts(at)) parts[part.type] = part.value;
  return asUtc(+parts.year, +parts.month, +parts.day, +parts.hour, +parts.minute, +parts.second) - Math.floor(at / 1000) * 1000;
}

// The moment a clock time on a day is in a time zone. Intl only goes the other way (moment to
// clock), so: read the clock as if it were UTC, take off the zone's offset then, and again in case
// summer time starts or ends in between. A zone this browser doesn't know: this device's own.
export function instantOf(day: string, time: string, zone: string): Date {
  const [year, month, date] = day.split("-").map(Number);
  const [hour, minute] = time.split(":").map(Number);
  const wall = asUtc(year, month, date, hour, minute);
  try {
    return new Date(wall - offset(wall - offset(wall, zone), zone));
  } catch {
    const local = toDate(day);
    local.setHours(hour, minute);
    return local;
  }
}

// The calendar day in a time zone at a moment; this device's if the zone is unknown here.
export function dayIn(zone: string, at: Date): string {
  try {
    const there = new Date(at.getTime() + offset(at.getTime(), zone));
    return `${String(there.getUTCFullYear()).padStart(4, "0")}-${pad(there.getUTCMonth() + 1)}-${pad(there.getUTCDate())}`;
  } catch {
    return localDay(at);
  }
}

// When a task is due as this device sees it: the day here (with a time, it can be another day than
// where it was set) and the moment, if it has a time. undefined: no due date.
function dueHere(task: DueFields): { day: string; at?: Date } | undefined {
  if (!task.due_date) return undefined;
  if (!task.due_time || !task.due_zone) return { day: task.due_date };
  const at = instantOf(task.due_date, task.due_time, task.due_zone);
  return { day: localDay(at), at };
}

// When a task is due, for sorting: a time is its moment; a date alone counts as the end of that day,
// here. undefined: no due date.
export function dueMoment(task: Pick<Task, "due_date" | "due_time" | "due_zone">): number | undefined {
  if (!task.due_date) return undefined;
  if (task.due_time && task.due_zone) return instantOf(task.due_date, task.due_time, task.due_zone).getTime();
  return toDate(addDays(task.due_date, 1)).getTime();
}

// What the picker starts with: the day, the time in this device's time, and the repeat.
export function dueInput(task: DueFields & { repeat?: string | null }): DueInput | null {
  const due = dueHere(task);
  if (!due) return null;
  return { date: due.day, time: due.at ? localClock(due.at) : null, repeat: task.repeat ?? null };
}

// "Today", "Tomorrow · 9:30 AM", "Overdue · Oct 15", "Overdue · 3:00 PM" (earlier today),
// "Wed, Oct 21 · 3:00 PM" (the coming week), "Nov 30", "Jan 5, 2027"; full is the whole date and
// time, for a tooltip. zone: this device's (a parameter for the tests). undefined: no due date.
export function dueOf(task: DueFields, now: Date, locale?: string, zone = deviceZone()): Due | undefined {
  const due = dueHere(task);
  if (!due) return undefined;
  const { day, at } = due;
  const today = localDay(now);
  const date = toDate(day);
  const time = at?.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });

  let full = date.toLocaleDateString(locale, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  if (time) full += `, ${time}`;
  const note = at && zoneNote(task, at, zone, locale);
  if (note) full += ` (${note})`;

  const options: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" };
  if (day.slice(0, 4) !== today.slice(0, 4)) options.year = "numeric";
  if (day > today && day < addDays(today, 7)) options.weekday = "short";
  const short = date.toLocaleDateString(locale, options);
  const withTime = (text: string) => (time ? `${text} · ${time}` : text);

  const late = task.status !== "done" && (at ? at < now : day < today);
  if (late) {
    const when = day === today ? time : time ? `${short}, ${time}` : short;
    return { kind: "overdue", label: `Overdue · ${when}`, full, note };
  }
  if (day === today) return { kind: "today", label: withTime("Today"), full, note };
  if (day === addDays(today, 1)) return { kind: "tomorrow", label: withTime("Tomorrow"), full, note };
  return { kind: "date", label: withTime(short), full, note };
}

// "3:00 PM New York time" ("Sat 9:00 PM …" when it's another day there): the time as it was set,
// for a device in another zone whose clock reads differently at that moment.
function zoneNote(task: DueFields, at: Date, zone: string, locale?: string): string | undefined {
  if (!task.due_date || !task.due_time || !task.due_zone || task.due_zone === zone) return undefined;
  const sameDay = localDay(at) === task.due_date;
  if (sameDay && localClock(at) === task.due_time) return undefined;
  const there = toDate(task.due_date);
  const [hour, minute] = task.due_time.split(":").map(Number);
  there.setHours(hour, minute);
  const clock = there.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
  const weekday = sameDay ? "" : `${there.toLocaleDateString(locale, { weekday: "short" })} `;
  const city = task.due_zone.split("/").pop()!.replaceAll("_", " ");
  return `${weekday}${clock} ${city} time`;
}

// The "Due today" filter: the open tasks due today here (at any time today), and the overdue ones.
export function dueToday(tasks: Task[], now: Date): Task[] {
  const today = localDay(now);
  return tasks.filter((task) => {
    const day = task.status !== "done" && dueHere(task)?.day;
    return !!day && day <= today;
  });
}
