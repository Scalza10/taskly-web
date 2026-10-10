// The Board screen: the current list's tasks in three columns, New, In progress and Done. Each
// card's button moves its task on: Start, Finish, Reopen; an In progress card also has Back (to
// New). On a desktop a card can also be dragged to another column; on a phone (where the columns
// stack and dragging fights scrolling) the buttons are the way. Done ends with "Clear done".
import { ArrowLeft, ArrowRight } from "lucide-react";
import { useState, type DragEvent } from "react";
import type { Status, Task, TaskList } from "./api";
import { Avatar, Empty } from "./Chrome";
import { ClearDone } from "./ClearDone";
import { STAGES, moveChange, stage } from "./stages";
import type { Enqueue } from "./useLocal";
import { useWide } from "./useWide";

export function BoardScreen({ list, enqueue }: { list: TaskList; enqueue: Enqueue }) {
  const wide = useWide();
  const [dragging, setDragging] = useState<Task | null>(null);
  const [over, setOver] = useState<Status | null>(null);

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
    const change = dragging && moveChange(dragging, status);
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
            {tasks.map((task) => (
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
                <div className="card-foot">
                  {task.created_by && (
                    <span className="by">
                      {wide ? <><Avatar name={task.created_by} size="sm" />{task.created_by}</> : `added by ${task.created_by}`}
                    </span>
                  )}
                  {back && (
                    <button
                      type="button"
                      className="action"
                      aria-label={`Back to ${stage(back).label}: ${task.title}`}
                      title={`Back to ${stage(back).label}`}
                      onClick={() => void enqueue({ method: "PATCH", path: `/api/tasks/${task.id}`, body: { status: back } })}
                    >
                      <ArrowLeft size={13} strokeWidth={2.5} aria-hidden="true" />
                      Back
                    </button>
                  )}
                  <button
                    type="button"
                    className="action"
                    aria-label={`${action}: ${task.title}`}
                    onClick={() => void enqueue({ method: "PATCH", path: `/api/tasks/${task.id}`, body: { status: next } })}
                  >
                    {action}
                    <ArrowRight size={13} strokeWidth={2.5} aria-hidden="true" />
                  </button>
                </div>
              </article>
            ))}
            {status === "done" && <ClearDone list={list} enqueue={enqueue} />}
          </section>
        );
      })}
    </div>
  );
}
