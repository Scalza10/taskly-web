// How a task repeats: a rule like "FREQ=WEEKLY;BYDAY=MO", a small part of iCalendar's RRULE plus
// FROM=DONE (counted from the day it's finished), as the server stores it (taskly/repeats.py says
// more). Finishing a repeating task makes the next one: nextDue is its due date, worked out here too
// so it shows while offline, and tested on the server's cases (repeat.cases.json). describeRule is
// what the chip says; presets, choiceOf and buildRule are the due date picker's Repeat choices.
// Dates are calendar days, "2026-10-19", worked out in UTC so no clock change gets in the way.

export type Freq = "DAILY" | "WEEKLY" | "MONTHLY" | "YEARLY";
// days: weekdays, Monday 0, as on the server.
export type Rule = { freq: Freq; interval: number; days: number[]; month?: number; monthDay?: number; fromDone: boolean };

const FREQS: Freq[] = ["DAILY", "WEEKLY", "MONTHLY", "YEARLY"];
const DAYS = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"];
const WEEKDAYS = [0, 1, 2, 3, 4];
const DAY_MS = 86_400_000;

// The rule in a stored text, or undefined if it isn't one (the server checks what it stores).
export function parseRule(text: string): Rule | undefined {
  const parts = new Map<string, string>();
  for (const piece of text.split(";")) {
    const [key, value] = piece.split("=");
    if (key && value !== undefined) parts.set(key.trim().toUpperCase(), value.trim().toUpperCase());
  }
  const freq = parts.get("FREQ") as Freq;
  if (!FREQS.includes(freq)) return undefined;
  const number = (key: string) => (parts.has(key) ? Number(parts.get(key)) || undefined : undefined);
  const days = parts.get("BYDAY")?.split(",").map((day) => DAYS.indexOf(day)).filter((day) => day >= 0) ?? [];
  return {
    freq, interval: number("INTERVAL") ?? 1, days: [...new Set(days)].sort(), month: number("BYMONTH"),
    monthDay: number("BYMONTHDAY"), fromDone: parts.get("FROM") === "DONE",
  };
}

// As the server stores it: parts in order, INTERVAL=1 left out.
export function formatRule(rule: Rule): string {
  const parts = [`FREQ=${rule.freq}`];
  if (rule.interval !== 1) parts.push(`INTERVAL=${rule.interval}`);
  if (rule.days.length) parts.push(`BYDAY=${[...rule.days].sort().map((day) => DAYS[day]).join(",")}`);
  if (rule.month) parts.push(`BYMONTH=${rule.month}`);
  if (rule.monthDay) parts.push(`BYMONTHDAY=${rule.monthDay}`);
  if (rule.fromDone) parts.push("FROM=DONE");
  return parts.join(";");
}

// A calendar day as UTC midnight, in ms. setUTCFullYear: Date.UTC would read years below 100 as 19xx.
function toMs(day: string): number {
  const [year, month, date] = day.split("-").map(Number);
  const at = new Date(0);
  at.setUTCFullYear(year, month - 1, date);
  return at.getTime();
}

function fromMs(ms: number): string {
  const at = new Date(ms);
  const pad = (n: number, width = 2) => String(n).padStart(width, "0");
  return `${pad(at.getUTCFullYear(), 4)}-${pad(at.getUTCMonth() + 1)}-${pad(at.getUTCDate())}`;
}

const yearOf = (ms: number) => new Date(ms).getUTCFullYear();
const weekdayOf = (ms: number) => (new Date(ms).getUTCDay() + 6) % 7; // Monday 0

// A calendar day's weekday, Monday 0.
export function dayOfWeek(date: string): number {
  return weekdayOf(toMs(date));
}

// That day of a month (index: year * 12 + month - 1), or the month's last if it has fewer days.
function inMonth(index: number, day: number): number {
  const year = Math.floor(index / 12);
  const month = index - year * 12;
  const last = new Date(0);
  last.setUTCFullYear(year, month + 1, 0);
  const at = new Date(0);
  at.setUTCFullYear(year, month, Math.min(day, last.getUTCDate()));
  return at.getTime();
}

const monthIndex = (ms: number) => yearOf(ms) * 12 + new Date(ms).getUTCMonth();

// The first day of the schedule after due that isn't before today; each starts in today's period
// (rounded down to the interval), as on the server. undefined past the year 9999.
function onSchedule(rule: Rule, due: number, today: number): number | undefined {
  const n = rule.interval;
  const fits = (at: number) => at > due && at >= today;
  if (rule.freq === "DAILY") return due + n * Math.max(1, Math.ceil((today - due) / DAY_MS / n)) * DAY_MS;
  if (rule.freq === "WEEKLY") {
    const monday = due - weekdayOf(due) * DAY_MS;
    const days = rule.days.length ? rule.days : [weekdayOf(due)];
    for (let weeks = Math.floor(Math.max(0, Math.floor((today - monday) / DAY_MS / 7)) / n) * n; ; weeks += n) {
      for (const day of days) {
        const at = monday + (weeks * 7 + day) * DAY_MS;
        if (yearOf(at) > 9999) return undefined;
        if (fits(at)) return at;
      }
    }
  }
  if (rule.freq === "MONTHLY") {
    const start = monthIndex(due);
    const day = rule.monthDay ?? new Date(due).getUTCDate();
    for (let months = Math.floor(Math.max(0, monthIndex(today) - start) / n) * n; ; months += n) {
      const at = inMonth(start + months, day);
      if (yearOf(at) > 9999) return undefined;
      if (fits(at)) return at;
    }
  }
  const month = rule.month ? rule.month - 1 : new Date(due).getUTCMonth();
  const day = rule.monthDay ?? new Date(due).getUTCDate();
  for (let years = Math.floor(Math.max(0, yearOf(today) - yearOf(due)) / n) * n; ; years += n) {
    const at = inMonth((yearOf(due) + years) * 12 + month, day);
    if (yearOf(at) > 9999) return undefined;
    if (fits(at)) return at;
  }
}

function afterDone(rule: Rule, today: number): number {
  const n = rule.interval;
  const date = new Date(today).getUTCDate();
  if (rule.freq === "DAILY") return today + n * DAY_MS;
  if (rule.freq === "WEEKLY") return today + 7 * n * DAY_MS;
  if (rule.freq === "MONTHLY") return inMonth(monthIndex(today) + n, date);
  return inMonth(monthIndex(today) + 12 * n, date);
}

// When the task after this one is due, finished today; null past 9999-12-31 (the series ends) or
// for a rule that isn't one.
export function nextDue(text: string, dueDate: string, today: string): string | null {
  const rule = parseRule(text);
  if (!rule) return null;
  const found = rule.fromDone ? afterDone(rule, toMs(today)) : onSchedule(rule, toMs(dueDate), toMs(today));
  // Compared as numbers: as text, "10000-01-01" sorts before "9999-12-31".
  return found === undefined || yearOf(found) > 9999 ? null : fromMs(found);
}

// "Monday" or "Mon", in the page's language, from a known Monday.
function dayName(day: number, width: "long" | "short", locale?: string): string {
  return new Date(Date.UTC(2024, 0, 1 + day)).toLocaleDateString(locale, { weekday: width, timeZone: "UTC" });
}

function ordinal(n: number): string {
  const tens = n % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ["th", "st", "nd", "rd"][n % 10] ?? "th";
  return `${n}${suffix}`;
}

// "Oct 19": 2000 is a leap year, so February 29th has a name too.
function monthDayName(month: number, day: number, locale?: string): string {
  return new Date(Date.UTC(2000, month - 1, day)).toLocaleDateString(locale, { month: "short", day: "numeric", timeZone: "UTC" });
}

function joined(names: string[]): string {
  return names.length < 2 ? names.join("") : `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}`;
}

const UNITS: Record<Freq, string> = { DAILY: "day", WEEKLY: "week", MONTHLY: "month", YEARLY: "year" };

// What the chip's tooltip says: "Every day", "Every weekday", "Every Monday", "Every Mon and Thu",
// "Every 2 weeks on Monday", "Every month on the 19th", "Every year on Oct 19", "3 days after it's done".
export function describeRule(text: string, locale?: string): string {
  const rule = parseRule(text);
  if (!rule) return "Repeats";
  const unit = UNITS[rule.freq];
  if (rule.fromDone) return rule.interval === 1 ? `A ${unit} after it's done` : `${rule.interval} ${unit}s after it's done`;
  const every = rule.interval === 1 ? `Every ${unit}` : `Every ${rule.interval} ${unit}s`;
  if (rule.freq === "WEEKLY" && rule.days.length) {
    const weekdays = rule.days.join() === WEEKDAYS.join();
    const names = joined(rule.days.map((day) => dayName(day, rule.days.length > 1 ? "short" : "long", locale)));
    if (rule.interval === 1) return weekdays ? "Every weekday" : `Every ${names}`;
    return `${every} on ${weekdays ? "weekdays" : names}`;
  }
  if (rule.freq === "MONTHLY" && rule.monthDay) return `${every} on the ${ordinal(rule.monthDay)}`;
  if (rule.freq === "YEARLY" && rule.month && rule.monthDay) return `${every} on ${monthDayName(rule.month, rule.monthDay, locale)}`;
  return every;
}

// The due date picker's Repeat choices. custom: every how many days, weeks, months or years; for
// weeks, which days; and whether it counts from the day it's finished.
export type Choice = "none" | "daily" | "weekdays" | "weekly" | "monthly" | "yearly" | "custom";
export type Custom = { interval: number; freq: Freq; days: number[]; fromDone: boolean };

// The choices' names for the date in the picker ("" while it has none: without the day).
export function presets(date: string, locale?: string): { choice: Choice; label: string }[] {
  const at = date ? new Date(toMs(date)) : undefined;
  const on = (name: (at: Date) => string) => (at ? ` on ${name(at)}` : "");
  return [
    { choice: "none", label: "Doesn't repeat" },
    { choice: "daily", label: "Every day" },
    { choice: "weekdays", label: "Every weekday (Mon–Fri)" },
    { choice: "weekly", label: `Every week${on((at) => dayName(weekdayOf(at.getTime()), "long", locale))}` },
    { choice: "monthly", label: `Every month${on((at) => `the ${ordinal(at.getUTCDate())}`)}` },
    { choice: "yearly", label: `Every year${on((at) => monthDayName(at.getUTCMonth() + 1, at.getUTCDate(), locale))}` },
    { choice: "custom", label: "Custom…" },
  ];
}

// The rule a choice makes for a task due on date, with every part the server would fill in from it
// (its weekday, its day of the month); null: it doesn't repeat.
export function buildRule(choice: Choice, custom: Custom, date: string): string | null {
  const at = toMs(date);
  const weekday = weekdayOf(at);
  const month = new Date(at).getUTCMonth() + 1;
  const monthDay = new Date(at).getUTCDate();
  const rule = (freq: Freq, extra: Partial<Rule> = {}) => formatRule({ freq, interval: 1, days: [], fromDone: false, ...extra });
  switch (choice) {
    case "none": return null;
    case "daily": return rule("DAILY");
    case "weekdays": return rule("WEEKLY", { days: WEEKDAYS });
    case "weekly": return rule("WEEKLY", { days: [weekday] });
    case "monthly": return rule("MONTHLY", { monthDay });
    case "yearly": return rule("YEARLY", { month, monthDay });
  }
  const interval = Math.min(999, Math.max(1, Math.round(custom.interval) || 1));
  if (custom.fromDone) return rule(custom.freq, { interval, fromDone: true });
  if (custom.freq === "WEEKLY") return rule("WEEKLY", { interval, days: custom.days.length ? custom.days : [weekday] });
  if (custom.freq === "MONTHLY") return rule("MONTHLY", { interval, monthDay });
  if (custom.freq === "YEARLY") return rule("YEARLY", { interval, month, monthDay });
  return rule("DAILY", { interval });
}

// What the picker shows for a task's rule on its date: the preset it is, else Custom with its parts.
export function choiceOf(text: string | null, date: string): { choice: Choice; custom: Custom } {
  const rule = text ? parseRule(text) : undefined;
  const custom: Custom = rule
    ? { interval: rule.interval, freq: rule.freq, days: rule.days, fromDone: rule.fromDone }
    : { interval: 1, freq: "WEEKLY", days: date ? [weekdayOf(toMs(date))] : [], fromDone: false };
  if (!rule) return { choice: "none", custom };
  const presetChoices: Choice[] = ["daily", "weekdays", "weekly", "monthly", "yearly"];
  const choice = presetChoices.find((each) => (date || each === "daily" || each === "weekdays") && buildRule(each, custom, date || "2000-01-03") === text);
  return { choice: choice ?? "custom", custom };
}
