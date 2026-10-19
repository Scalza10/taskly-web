import { expect, test } from "vitest";
import cases from "./repeat.cases.json";
import { buildRule, choiceOf, describeRule, formatRule, nextDue, parseRule, presets, type Choice, type Custom } from "./repeat";

// The server's cases (tests/test_repeats.py runs them too): the page shows the next task offline
// on the day the server will make it.
test.each(cases)("the next one: $why", ({ rule, due, today, next }) => {
  expect(nextDue(rule, due, today)).toBe(next);
});

test("a stored rule reads back as it was", () => {
  for (const { rule } of cases) expect(formatRule(parseRule(rule)!)).toBe(rule);
  expect(parseRule("FREQ=HOURLY")).toBeUndefined();
  expect(parseRule("")).toBeUndefined();
  expect(nextDue("nonsense", "2026-10-19", "2026-10-19")).toBeNull();
});

test("what the chip says", () => {
  const says = (rule: string) => describeRule(rule, "en-US");
  expect(says("FREQ=DAILY")).toBe("Every day");
  expect(says("FREQ=DAILY;INTERVAL=3")).toBe("Every 3 days");
  expect(says("FREQ=WEEKLY;BYDAY=MO")).toBe("Every Monday");
  expect(says("FREQ=WEEKLY;BYDAY=MO,TH")).toBe("Every Mon and Thu");
  expect(says("FREQ=WEEKLY;BYDAY=MO,WE,FR")).toBe("Every Mon, Wed and Fri");
  expect(says("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR")).toBe("Every weekday");
  expect(says("FREQ=WEEKLY;INTERVAL=2;BYDAY=FR")).toBe("Every 2 weeks on Friday");
  expect(says("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH")).toBe("Every 2 weeks on Mon and Thu");
  expect(says("FREQ=MONTHLY;BYMONTHDAY=1")).toBe("Every month on the 1st");
  expect(says("FREQ=MONTHLY;BYMONTHDAY=22")).toBe("Every month on the 22nd");
  expect(says("FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=13")).toBe("Every 3 months on the 13th");
  expect(says("FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=19")).toBe("Every year on Oct 19");
  expect(says("FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29")).toBe("Every year on Feb 29");
  expect(says("FREQ=DAILY;INTERVAL=3;FROM=DONE")).toBe("3 days after it's done");
  expect(says("FREQ=WEEKLY;FROM=DONE")).toBe("A week after it's done");
  expect(says("x")).toBe("Repeats");
});

test("the picker's choices name the day in the field, or none while it's empty", () => {
  const labels = (date: string) => presets(date, "en-US").map((preset) => preset.label);
  expect(labels("2026-10-19")).toEqual([
    "Doesn't repeat", "Every day", "Every weekday (Mon–Fri)", "Every week on Monday", "Every month on the 19th",
    "Every year on Oct 19", "Custom…",
  ]);
  expect(labels("")).toContain("Every week");
});

const custom = (extra: Partial<Custom> = {}): Custom => ({ interval: 1, freq: "WEEKLY", days: [], fromDone: false, ...extra });

test("each choice makes a rule with the date's own parts", () => {
  const built = (choice: Choice, extra?: Partial<Custom>) => buildRule(choice, custom(extra), "2026-10-31");
  expect(built("none")).toBeNull();
  expect(built("daily")).toBe("FREQ=DAILY");
  expect(built("weekdays")).toBe("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR");
  expect(built("weekly")).toBe("FREQ=WEEKLY;BYDAY=SA");
  expect(built("monthly")).toBe("FREQ=MONTHLY;BYMONTHDAY=31");
  expect(built("yearly")).toBe("FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=31");
  expect(built("custom", { interval: 2, days: [3, 0] })).toBe("FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH");
  expect(built("custom", { interval: 2 })).toBe("FREQ=WEEKLY;INTERVAL=2;BYDAY=SA"); // no day picked: the date's
  expect(built("custom", { interval: 3, freq: "MONTHLY" })).toBe("FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=31");
  expect(built("custom", { interval: 1, freq: "YEARLY" })).toBe("FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=31");
  expect(built("custom", { interval: 4, freq: "DAILY" })).toBe("FREQ=DAILY;INTERVAL=4");
  expect(built("custom", { interval: 3, freq: "DAILY", fromDone: true, days: [1] })).toBe("FREQ=DAILY;INTERVAL=3;FROM=DONE");
  expect(built("custom", { interval: 0 })).toBe("FREQ=WEEKLY;BYDAY=SA");
  expect(built("custom", { interval: 5000, freq: "DAILY" })).toBe("FREQ=DAILY;INTERVAL=999");
});

test("the picker opens on the task's rule: a preset if it is one, else Custom", () => {
  expect(choiceOf(null, "2026-10-19")).toEqual({ choice: "none", custom: custom({ days: [0] }) });
  expect(choiceOf("FREQ=DAILY", "2026-10-19").choice).toBe("daily");
  expect(choiceOf("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "2026-10-19").choice).toBe("weekdays");
  expect(choiceOf("FREQ=WEEKLY;BYDAY=MO", "2026-10-19").choice).toBe("weekly");
  expect(choiceOf("FREQ=MONTHLY;BYMONTHDAY=19", "2026-10-19").choice).toBe("monthly");
  expect(choiceOf("FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=19", "2026-10-19").choice).toBe("yearly");
  // Not the date's: Custom, with its parts.
  expect(choiceOf("FREQ=WEEKLY;BYDAY=TU", "2026-10-19")).toEqual({ choice: "custom", custom: custom({ days: [1] }) });
  expect(choiceOf("FREQ=MONTHLY;BYMONTHDAY=31", "2027-02-28")).toEqual({ choice: "custom", custom: custom({ freq: "MONTHLY" }) });
  expect(choiceOf("FREQ=DAILY;INTERVAL=3;FROM=DONE", "2026-10-19")).toEqual({
    choice: "custom", custom: custom({ interval: 3, freq: "DAILY", fromDone: true }),
  });
  // And each choice round-trips.
  for (const choice of ["daily", "weekdays", "weekly", "monthly", "yearly"] as Choice[]) {
    expect(choiceOf(buildRule(choice, custom(), "2026-10-19"), "2026-10-19").choice).toBe(choice);
  }
});
