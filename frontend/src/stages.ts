// A task's stage (its status) as the screens show it: the List's chip, the Board's columns and
// buttons, the List's headline and the Focus screen's "Working on".
import type { Status, Task } from "./api";
import type { TaskChange } from "./store";

// back: the stage a task can be sent back to (In progress → New, if it was started too soon).
export const STAGES: { status: Status; label: string; action: string; next: Status; back?: Status }[] = [
  { status: "new", label: "New", action: "Start", next: "progress" },
  { status: "progress", label: "In progress", action: "Finish", next: "done", back: "new" },
  { status: "done", label: "Done", action: "Reopen", next: "new" },
];

export function stage(status: Status) {
  return STAGES.find((s) => s.status === status)!;
}

// A Board card dropped on a column: the change that moves it there; none on its own column.
export function moveChange(task: Task, status: Status): TaskChange | undefined {
  if (task.status === status) return undefined;
  return { method: "PATCH", path: `/api/tasks/${task.id}`, body: { status } };
}

const WORDS = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];

// "All clear.", "One thing to tend to.", "Four things to tend to.", "12 things to tend to."
export function headline(tasks: Task[]): string {
  const open = tasks.filter((task) => task.status !== "done").length;
  if (open === 0) return "All clear.";
  if (open === 1) return "One thing to tend to.";
  return `${WORDS[open] ?? open} things to tend to.`;
}

// The first task in progress, else the first new one.
export function workingOn(tasks: Task[]): Task | undefined {
  return tasks.find((task) => task.status === "progress") ?? tasks.find((task) => task.status === "new");
}

// The Focus screen's task: the one picked, if it's open in these tasks; else the one working on.
export function focusTask(tasks: Task[], picked: string | null): Task | undefined {
  return tasks.find((task) => task.id === picked && task.status !== "done") ?? workingOn(tasks);
}
