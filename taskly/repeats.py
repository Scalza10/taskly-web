"""How a task repeats: a rule in a small part of iCalendar's RRULE (agents know it, and a calendar
feed can use it), on a task with a due date. Finishing a repeating task makes the next one
(tasks.update_task); next_due works out when it's due. frontend/src/repeat.ts does the same for
the page, and both are tested on frontend/src/repeat.cases.json.

  FREQ=DAILY|WEEKLY|MONTHLY|YEARLY   required
  INTERVAL=n                         every n days, weeks, months or years (1 to 999; left out, 1)
  BYDAY=MO,TH                        weekly only: the days of the week
  BYMONTH=m                          yearly only, with BYMONTHDAY
  BYMONTHDAY=d                       monthly and yearly: the day (past the month's end, its last day)
  FROM=DONE                          ours, not iCalendar's: counted from the day it's finished, not
                                     the schedule; no BY parts

On the schedule, the next one is the first day of it after the due date that isn't before today:
missed ones are skipped. Weeks count from the due date's week (Monday first), as in iCalendar.
Stored rules are canonical (parts in the order above, INTERVAL=1 left out) and anchored: a part
left out is the due date's (its weekday, day, month), so a task due on the 31st stays on month ends.
Dates are '2026-10-19', as tasks store them. Any rule that isn't one is a ValueError, never another
error: a page's change answered with a 500 would be sent again forever."""

import re
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

FREQS = ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")  # date.weekday() order
PARTS = ("FREQ", "INTERVAL", "BYDAY", "BYMONTH", "BYMONTHDAY", "FROM")
# The most days a month can have (February's in a leap year).
MONTH_DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True)
class Rule:
    freq: str
    interval: int = 1
    days: tuple[int, ...] = ()  # weekdays, Monday 0
    month: int | None = None
    month_day: int | None = None
    from_done: bool = False


def _number(parts: dict[str, str], key: str, highest: int) -> int | None:
    if key not in parts:
        return None
    if not re.fullmatch(r"[0-9]{1,4}", parts[key]) or not 1 <= int(parts[key]) <= highest:
        raise ValueError(f"{key} is a number from 1 to {highest}")
    return int(parts[key])


def parse(rule: str) -> Rule:
    """The rule in text (any case, spaces, an RRULE: prefix, parts in any order); ValueError if it isn't one."""
    parts: dict[str, str] = {}
    for piece in filter(None, (piece.strip() for piece in rule.strip().upper().removeprefix("RRULE:").split(";"))):
        key, equals, value = (part.strip() for part in piece.partition("="))
        if not equals or key not in PARTS:
            raise ValueError(f'"{piece}" isn\'t part of a repeat: use {", ".join(PARTS)}, like FREQ=WEEKLY;BYDAY=MO')
        if key in parts:
            raise ValueError(f"{key} is given twice")
        parts[key] = value
    freq = parts.get("FREQ")
    if freq not in FREQS:
        raise ValueError("a repeat needs FREQ=DAILY, WEEKLY, MONTHLY or YEARLY")
    days: list[int] = []
    for day in (day.strip() for day in parts["BYDAY"].split(",")) if "BYDAY" in parts else ():
        if day not in DAYS or DAYS.index(day) in days:
            raise ValueError("BYDAY is days of the week, each once: MO, TU, WE, TH, FR, SA, SU")
        days.append(DAYS.index(day))
    if parts.get("FROM", "DONE") != "DONE":
        raise ValueError("FROM can only be DONE")
    rule = Rule(freq, _number(parts, "INTERVAL", 999) or 1, tuple(sorted(days)), _number(parts, "BYMONTH", 12),
                _number(parts, "BYMONTHDAY", 31), "FROM" in parts)
    if rule.days and freq != "WEEKLY":
        raise ValueError("BYDAY goes only with FREQ=WEEKLY")
    if rule.month_day and freq not in ("MONTHLY", "YEARLY"):
        raise ValueError("BYMONTHDAY goes only with FREQ=MONTHLY or YEARLY")
    if rule.month and freq != "YEARLY":
        raise ValueError("BYMONTH goes only with FREQ=YEARLY")
    if freq == "YEARLY" and (rule.month is None) != (rule.month_day is None):
        raise ValueError("BYMONTH and BYMONTHDAY come together")
    if rule.month and rule.month_day > MONTH_DAYS[rule.month - 1]:
        raise ValueError(f"month {rule.month} has no day {rule.month_day}")
    if rule.from_done and (rule.days or rule.month or rule.month_day):
        raise ValueError("FROM=DONE counts from the day it's finished: no BYDAY, BYMONTH or BYMONTHDAY")
    return rule


def as_text(rule: Rule) -> str:
    parts = [f"FREQ={rule.freq}"]
    if rule.interval != 1:
        parts.append(f"INTERVAL={rule.interval}")
    if rule.days:
        parts.append("BYDAY=" + ",".join(DAYS[day] for day in rule.days))
    if rule.month:
        parts.append(f"BYMONTH={rule.month}")
    if rule.month_day:
        parts.append(f"BYMONTHDAY={rule.month_day}")
    if rule.from_done:
        parts.append("FROM=DONE")
    return ";".join(parts)


def canonical(rule: str) -> str:
    """The rule as stored, or a ValueError for whoever sent it. "" stays "": no repeat."""
    return as_text(parse(rule)) if rule.strip() else ""


def anchored(rule: str, due_date: str) -> str:
    """The rule with the parts it left out taken from the due date: its weekday, day of the month, month."""
    parsed, due = parse(rule), date.fromisoformat(due_date)
    if parsed.from_done:
        return as_text(parsed)
    if parsed.freq == "WEEKLY" and not parsed.days:
        parsed = replace(parsed, days=(due.weekday(),))
    if parsed.freq == "MONTHLY" and not parsed.month_day:
        parsed = replace(parsed, month_day=due.day)
    if parsed.freq == "YEARLY" and not parsed.month:
        parsed = replace(parsed, month=due.month, month_day=due.day)
    return as_text(parsed)


def moved(rule: str, old_date: str, new_date: str) -> str:
    """The rule of a task whose due date moved: one anchored on the old date ("every week" set on a
    Monday) moves with it; one that says more ("every weekday", "the 31st") stays as it is."""
    bare = as_text(replace(parse(rule), days=(), month=None, month_day=None))
    return anchored(bare, new_date) if anchored(bare, old_date) == rule else rule


def _day(year: int, month: int, day: int) -> date:
    """That day, or the month's last if it has fewer days."""
    return date(year, month, min(day, monthrange(year, month)[1]))


def _in_month(index: int, day: int) -> date:
    """Day of the month at index (year * 12 + month - 1)."""
    return _day(index // 12, index % 12 + 1, day)


def _on_schedule(rule: Rule, due: date, today: date) -> date:
    """The first day of the schedule after due that isn't before today. Each starts in the period
    of today (rounded down to the interval) so a long-overdue task doesn't step through the years."""
    n = rule.interval
    if rule.freq == "DAILY":
        return due + timedelta(days=n * max(1, -(-(today - due).days // n)))
    if rule.freq == "WEEKLY":
        monday = due - timedelta(days=due.weekday())
        weeks = max(0, (today - monday).days // 7) // n * n
        while True:
            for weekday in rule.days or (due.weekday(),):
                found = monday + timedelta(weeks=weeks, days=weekday)
                if found > due and found >= today:
                    return found
            weeks += n
    if rule.freq == "MONTHLY":
        start = due.year * 12 + due.month - 1
        months = max(0, today.year * 12 + today.month - 1 - start) // n * n
        while True:
            found = _in_month(start + months, rule.month_day or due.day)
            if found > due and found >= today:
                return found
            months += n
    years = max(0, today.year - due.year) // n * n
    while True:
        found = _day(due.year + years, rule.month or due.month, rule.month_day or due.day)
        if found > due and found >= today:
            return found
        years += n


def _after_done(rule: Rule, today: date) -> date:
    n = rule.interval
    if rule.freq == "DAILY":
        return today + timedelta(days=n)
    if rule.freq == "WEEKLY":
        return today + timedelta(weeks=n)
    if rule.freq == "MONTHLY":
        return _in_month(today.year * 12 + today.month - 1 + n, today.day)
    return _day(today.year + n, today.month, today.day)


def next_due(rule: str, due_date: str, today: str) -> str | None:
    """When the task after this one is due, finished today; None past 9999-12-31 (the series ends)."""
    parsed, due, now = parse(rule), date.fromisoformat(due_date), date.fromisoformat(today)
    try:
        found = _after_done(parsed, now) if parsed.from_done else _on_schedule(parsed, due, now)
    except (OverflowError, ValueError):  # a date past the year 9999
        return None
    return found.isoformat()


def today_for(due_zone: str | None) -> str:
    """Today for a task finished without the finisher's date (an older page, an agent that didn't say): in its time
    zone if it has a time, else UTC's, as the server knows no other. A day off late in the evening west
    of UTC, which matters only to FROM=DONE and to skipping missed days."""
    return datetime.now(ZoneInfo(due_zone) if due_zone else UTC).date().isoformat()
