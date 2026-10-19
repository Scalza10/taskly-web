import json
import random
from pathlib import Path

import pytest

from taskly import repeats

# The same cases test frontend/src/repeat.ts, so the page and the server agree on the next day.
CASES = json.loads((Path(__file__).parents[1] / "frontend" / "src" / "repeat.cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[case["why"] for case in CASES])
def test_next_due(case):
    assert repeats.next_due(case["rule"], case["due"], case["today"]) == case["next"]


def test_the_cases_are_canonical_rules():
    for case in CASES:
        assert repeats.canonical(case["rule"]) == case["rule"]


@pytest.mark.parametrize(("sent", "stored"), [
    ("FREQ=DAILY", "FREQ=DAILY"),
    ("freq=weekly; byday=th,mo", "FREQ=WEEKLY;BYDAY=MO,TH"),
    ("RRULE:FREQ=WEEKLY;INTERVAL=1;BYDAY=MO;", "FREQ=WEEKLY;BYDAY=MO"),
    ("BYMONTHDAY=31;FREQ=MONTHLY;INTERVAL=02", "FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=31"),
    ("FREQ=YEARLY;BYMONTHDAY=29;BYMONTH=2", "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29"),
    ("FREQ=DAILY;INTERVAL=3;FROM=DONE", "FREQ=DAILY;INTERVAL=3;FROM=DONE"),
    ("  ", ""),
])
def test_canonical(sent, stored):
    assert repeats.canonical(sent) == stored


@pytest.mark.parametrize("sent", [
    "DAILY", "FREQ", "FREQ=", "FREQ=HOURLY", "INTERVAL=2", "FREQ=DAILY;FREQ=DAILY", "FREQ=DAILY;COUNT=3",
    "FREQ=DAILY;INTERVAL=0", "FREQ=DAILY;INTERVAL=1000", "FREQ=DAILY;INTERVAL=-1", "FREQ=DAILY;INTERVAL=²",
    "FREQ=WEEKLY;BYDAY=", "FREQ=WEEKLY;BYDAY=MO,MO", "FREQ=WEEKLY;BYDAY=1MO", "FREQ=WEEKLY;BYDAY=MO,",
    "FREQ=DAILY;BYDAY=MO", "FREQ=WEEKLY;BYMONTHDAY=3", "FREQ=MONTHLY;BYMONTHDAY=32", "FREQ=MONTHLY;BYMONTH=2",
    "FREQ=YEARLY;BYMONTH=2", "FREQ=YEARLY;BYMONTHDAY=2", "FREQ=YEARLY;BYMONTH=4;BYMONTHDAY=31",
    "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30", "FREQ=MONTHLY;BYMONTHDAY=5;FROM=DONE", "FREQ=DAILY;FROM=DUE",
    "FREQ=WEEKLY;BYDAY=MO;FROM=DONE", "FREQ=DAILY;FROM=",
])
def test_what_isnt_a_rule_is_a_value_error(sent):
    with pytest.raises(ValueError):
        repeats.canonical(sent)


def test_junk_is_only_ever_a_value_error():
    # A KeyError or IndexError would be a 500, and the page would send the change again forever.
    pieces = ["FREQ", "=", ";", ",", "DAILY", "WEEKLY", "MONTHLY", "YEARLY", "BYDAY", "MO", "SU", "BYMONTH",
              "BYMONTHDAY", "INTERVAL", "FROM", "DONE", "0", "1", "12", "31", "999", "RRULE:", " ", "\ud800", "é"]
    chance = random.Random(9)
    for _ in range(3000):
        text = "".join(chance.choice(pieces) for _ in range(chance.randint(1, 12)))
        try:
            repeats.canonical(text)
        except ValueError:
            pass


@pytest.mark.parametrize(("rule", "due", "stored"), [
    ("FREQ=WEEKLY", "2026-10-21", "FREQ=WEEKLY;BYDAY=WE"),
    ("FREQ=WEEKLY;INTERVAL=2", "2026-10-21", "FREQ=WEEKLY;INTERVAL=2;BYDAY=WE"),
    ("FREQ=WEEKLY;BYDAY=MO,TH", "2026-10-21", "FREQ=WEEKLY;BYDAY=MO,TH"),
    ("FREQ=MONTHLY", "2026-10-31", "FREQ=MONTHLY;BYMONTHDAY=31"),
    ("FREQ=YEARLY", "2028-02-29", "FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=29"),
    ("FREQ=DAILY", "2026-10-21", "FREQ=DAILY"),
    ("FREQ=MONTHLY;FROM=DONE", "2026-10-31", "FREQ=MONTHLY;FROM=DONE"),
])
def test_anchored_fills_in_the_due_dates_parts(rule, due, stored):
    assert repeats.anchored(rule, due) == stored


@pytest.mark.parametrize(("rule", "old", "new", "stored"), [
    # Set from the old date: it follows the date.
    ("FREQ=WEEKLY;BYDAY=MO", "2026-10-19", "2026-10-20", "FREQ=WEEKLY;BYDAY=TU"),
    ("FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=19", "2026-10-19", "2026-10-05", "FREQ=MONTHLY;INTERVAL=2;BYMONTHDAY=5"),
    ("FREQ=YEARLY;BYMONTH=10;BYMONTHDAY=19", "2026-10-19", "2026-12-25", "FREQ=YEARLY;BYMONTH=12;BYMONTHDAY=25"),
    # Says more than the old date: it stays.
    ("FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR", "2026-10-19", "2026-10-20", "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"),
    ("FREQ=WEEKLY;BYDAY=MO", "2026-10-21", "2026-10-22", "FREQ=WEEKLY;BYDAY=MO"),
    ("FREQ=MONTHLY;BYMONTHDAY=31", "2027-02-28", "2027-03-15", "FREQ=MONTHLY;BYMONTHDAY=31"),
    # Nothing to follow.
    ("FREQ=DAILY;INTERVAL=3;FROM=DONE", "2026-10-19", "2026-10-25", "FREQ=DAILY;INTERVAL=3;FROM=DONE"),
])
def test_a_rule_set_from_the_due_date_moves_with_it(rule, old, new, stored):
    assert repeats.moved(rule, old, new) == stored


def test_today_for_a_task_is_in_its_zone():
    assert len(repeats.today_for(None)) == 10
    # Kiritimati and Niue are 25 hours apart: their dates always differ.
    assert repeats.today_for("Pacific/Kiritimati") != repeats.today_for("Pacific/Niue")
