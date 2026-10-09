// The Board screen: the current list's tasks in three columns, New, In progress and Done. Each
// card's button moves its task on: Start, Finish, Reopen. On a phone the columns stack.
import { ArrowRight } from "lucide-react";
import type { TaskList } from "./api";
import { Avatar, Empty } from "./Chrome";
import { STAGES } from "./stages";
import type { Enqueue } from "./useLocal";
import { useWide } from "./useWide";

export function BoardScreen({ list, enqueue }: { list: TaskList; enqueue: Enqueue }) {
  const wide = useWide();
  return (
    <div className="screen board-screen">
      <h1 className="visually-hidden">{list.name}</h1>
      {STAGES.map(({ status, label, action, next }) => {
        const tasks = list.tasks.filter((task) => task.status === status);
        return (
          <section key={status} className={`column column-${status}`} aria-label={label}>
            <h2 className="column-head">
              <span className="pebble pebble-a dot" aria-hidden="true" />
              <span className="column-label">{label}</span>
              <span className="count">{tasks.length}</span>
            </h2>
            {tasks.length === 0 && <Empty>Nothing here yet.</Empty>}
            {tasks.map((task) => (
              <article key={task.id} className={["board-card", status === "done" && "done", task.pending && "pending"].filter(Boolean).join(" ")}>
                <p className="card-title">{task.title}</p>
                <div className="card-foot">
                  {task.created_by && (
                    <span className="by">
                      {wide ? <><Avatar name={task.created_by} size="sm" />{task.created_by}</> : `added by ${task.created_by}`}
                    </span>
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
          </section>
        );
      })}
    </div>
  );
}
