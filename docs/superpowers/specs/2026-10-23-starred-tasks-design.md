# Starred tasks (schema 10)

## Context

Enhancements item "Priority or a star, sorted to the top". The tasks the user most wants to flag
usually have no due date, and since due-dated tasks sort first, those sink under them.

Decided with the user (2026-10-23):
- **A star**, on or off: not priority levels.
- **Starred goes above everything open**, overdue tasks included. Done tasks stay at the bottom.
- **Shared**: part of the task, like its due date. Everyone on the list, and agents, see and change
  the same star.
- **Today gets a Starred section**, so flagged tasks without a date show there too.

## Design

- **Sort** (server `tasks.list_tasks`, page `view.sortTasks`): not done → starred → with a due
  date, soonest moment first → oldest first.
- **Storage**: `tasks.starred INTEGER NOT NULL DEFAULT 0 CHECK (starred IN (0, 1))`, sent as a bool.
- **API**: `POST /api/tasks` and `PATCH /api/tasks/{id}` take an optional `starred`; left out or
  `null`, it stays, so queues from older pages are unaffected. Finishing keeps the star; a
  repeating task's next one copies it, on the server (`_make_next`) and offline (`applyQueue`).
- **Agents**: `add_tasks`' items and `update_task` take an optional `starred` (`null` keeps it, as
  for their other arguments); answers show it; `list_tasks` sorts as the page does.
- **Page**: a star toggle on each task row and Board card (on a done task, shown only if starred).
  Today's first section, Starred, holds every open starred task from every list whatever its date or
  status, so a starred overdue task shows there and not under Overdue: the List's "above all" rule.
  The headline counts it.

Calls made while building (not asked):
- No star in the add bar: star after adding, which keeps the bar small.
- On a phone the star sits on the title's row by the ×, and the timer moves to the row below, so
  the title keeps its width; on a desktop the star is a column before the timer.
- The filled star uses the brand color (`--brand`), in both palettes.
