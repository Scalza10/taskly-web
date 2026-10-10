---
name: tracking-enhancements
description: Use when the user asks what's next for Taskly, how the enhancements or roadmap are going, wants to add, start, finish, drop or reorder an idea for the app, or when work begins or ships on a Taskly feature that may be on the Enhancements list.
---

# Tracking enhancements

## Overview

Taskly's planned features are tasks in its own **Enhancements** list (id
`2da2cbb1-ca7e-44ec-a081-41f4161986ed`), read and changed through the claude.ai Taskly connector.
The list is the progress board: its status is what's true, so keep it current as work happens,
not at the end.

## Connecting

The tools are deferred. Load them in one call:

`ToolSearch` → `select:mcp__claude_ai_Taskly__list_lists,mcp__claude_ai_Taskly__list_tasks,mcp__claude_ai_Taskly__add_tasks,mcp__claude_ai_Taskly__set_task_status,mcp__claude_ai_Taskly__complete_task,mcp__claude_ai_Taskly__update_task,mcp__claude_ai_Taskly__delete_task`

If a call answers "needs you to sign in again", ask the user to run `/mcp` and pick claude.ai
Taskly; don't retry until they have.

## Conventions

- **Title:** `[Tag] Short name: details`. Tags: `[Small]` (a short session), `[Medium]`,
  `[Google]` (Gmail, Calendar, Google Tasks). Tasks have no notes yet, so details go in the title
  (500 characters at most).
- **Status:** `new` = not started; `progress` = work has begun (design talk, a plan, or code);
  `done` = committed and pushed to `main`. Deploying is the user's step. Say "deploy pending" only
  for an item pushed in this conversation that the user hasn't said they deployed; otherwise say
  nothing about deploys (memory and git can't tell what's on the VM).
- **Order means nothing** (items added together share a timestamp). Priority is the user's call:
  asked what's next, recommend one item with the reason (what it unblocks, its size), then ask
  before moving it to In progress.
- Touch only this list. The user's other lists are personal.

## Quick reference

| User says / situation | Do |
|---|---|
| "What's next?" / "Where are we?" | `list_tasks(list=<the id>, include_done=true)`; show In progress, then New by tag, then a count of Done; leave out empty sections |
| Starting work on an item | `set_task_status(task_id, "progress")` before the work starts |
| The item's commit is pushed to `main` | `set_task_status(task_id, "done")`, then tell the user |
| Work stopped or was started too soon | `set_task_status(task_id, "new")` |
| New idea | `add_tasks(list=<the id>, titles=["[Tag] Name: details"])` |
| A feature shipped that isn't on the list | Offer to add it and mark it done; don't add it unasked |
| Rename an item | `update_task(task_id, title)` |
| Delete an item | Ask the user first, then `delete_task(task_id)` (no undo) |
| Merge two items | `update_task` the one that stays, then (after asking) `delete_task` the other |

Task ids come from `list_tasks`; match the user's words to a title, and ask if two could match.

## Common mistakes

- Marking an item done when the code is written but not pushed, or leaving it in progress after
  the push.
- Adding a duplicate: read the list first and check for a matching title.
- Shipping part of an item: leave it in progress and say what's left, or ask the user whether to
  split it into a new task for the rest.
- When `[Small] Notes on a task` ships, update this skill: details move to notes (and
  `update_task` may then take them).
