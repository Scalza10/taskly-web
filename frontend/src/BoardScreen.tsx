// The Board screen: the current list's tasks in three columns, New, In progress and Done. Each
// card's button moves its task on: Start, Finish, Reopen; an In progress card also has Back (to
// New). On a desktop a card can also be dragged to another column; on a phone (where the columns
// stack and dragging fights scrolling) the buttons are the way. An open card's timer button focuses
// on it on the Focus screen. A card with a due date or notes shows them (the notes' first two lines;
// a repeating task's date with the repeat mark; set them on the List screen). Done ends with "Clear done".
import { ArrowLeft, ArrowRight, CalendarDays, Repeat, Timer } from "lucide-react";
import { useState, type DragEvent } from "react";
import type { Status, Task, TaskList } from "./api";
import { Avatar, Empty } from "./Chrome";
import { ClearDone } from "./ClearDone";
import { dueOf } from "./due";
import { describeRule } from "./repeat";
import { NotesText } from "./TaskNotes";
import { STAGES, stage, statusChange } from "./stages";
import type { Enqueue } from "./useLocal";
import { useWide } from "./useWide";

type Props = { list: TaskList; enqueue: Enqueue; onFocus: (taskId: string) => void };

export function BoardScreen({ list, enqueue, onFocus }: Props) {
  const wide = useWide();
  const [dragging, setDragging] = useState<Task | null>(null);
  const [over, setOver] = useState<Status | null>(null);
  const now = new Date();

  function endDrag() {
    setDragging(null);
    setOver(null);
  }

  // Only a card from this page, and only onto another column: elsewhere the browser shows "no drop".
  function onDragOver(event: DragEvent, status: Status) {
    if (!dragging || dragging.status === status) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setOver(status);
  }

  function onDragLeave(event: DragEvent) {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(null);
  }

  function onDrop(event: DragEvent, status: Status) {
    event.preventDefault();
    const change = dragging && statusChange(dragging, status);
    endDrag();
    if (change) void enqueue(change);
  }

  return (
    <div className="screen board-screen">
      <h1 className="visually-hidden">{list.name}</h1>
      {STAGES.map(({ status, label, action, next, back }) => {
        const tasks = list.tasks.filter((task) => task.status === status);
        return (
          <section
            key={status}
            className={["column", `column-${status}`, over === status && "drop-target"].filter(Boolean).join(" ")}
            aria-label={label}
            onDragOver={(e) => onDragOver(e, status)}
            onDragLeave={onDragLeave}
            onDrop={(e) => onDrop(e, status)}
          >
            <h2 className="column-head">
              <span className="pebble pebble-a dot" aria-hidden="true" />
              <span className="column-label">{label}</span>
              <span className="count">{tasks.length}</span>
            </h2>
            {tasks.length === 0 && <Empty>Nothing here yet.</Empty>}
            {tasks.map((task) => {
              const due = dueOf(task, now);
              return (
                <article
                  key={task.id}
                  className={["board-card", status === "done" && "done", task.pending && "pending", dragging?.id === task.id && "dragging"].filter(Boolean).join(" ")}
                  draggable={wide}
                  onDragStart={(e) => {
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", task.title); // Firefox starts a drag only with data
                    setDragging(task);
                  }}
                  onDragEnd={endDrag}
                >
                  <p className="card-title">{task.title}</p>
                  {task.notes && <p className="card-notes"><NotesText text={task.notes} /></p>}
                  {due && (
                    <span className={`due due-${due.kind}`} title={task.repeat ? `${due.full} · ${describeRule(task.repeat)}` : due.full}>
                      <CalendarDays aria-hidden="true" />
                      {due.label}
                      {task.repeat && <Repeat role="img" aria-label={describeRule(task.repeat)} />}
                    </span>
                  )}
                  <div className="card-foot">
                    {task.created_by && (
                      <span className="by">
                        {wide ? <><Avatar name={task.created_by} size="sm" />{task.created_by}</> : `added by ${task.created_by}`}
                      </span>
                    )}
                    {status !== "done" && (
                      <button type="button" className="action icon-action" aria-label={`Focus on: ${task.title}`} title="Focus on this" onClick={() => onFocus(task.id)}>
                        <Timer size={14} strokeWidth={2.5} aria-hidden="true" />
                      </button>
                    )}
                    {back && (
                      <button
                        type="button"
                        className="action"
                        aria-label={`Back to ${stage(back).label}: ${task.title}`}
                        title={`Back to ${stage(back).label}`}
                        onClick={() => void enqueue(statusChange(task, back)!)}
                      >
                        <ArrowLeft size={13} strokeWidth={2.5} aria-hidden="true" />
                        Back
                      </button>
                    )}
                    <button
                      type="button"
                      className="action"
                      aria-label={`${action}: ${task.title}`}
                      onClick={() => void enqueue(statusChange(task, next)!)}
                    >
                      {action}
                      <ArrowRight size={13} strokeWidth={2.5} aria-hidden="true" />
                    </button>
                  </div>
                </article>
              );
            })}
            {status === "done" && <ClearDone list={list} enqueue={enqueue} />}
          </section>
        );
      })}
    </div>
  );
}
