// Talks to the FastAPI backend. JSON in and out; errors become ApiError with the HTTP status.

// new → progress (in progress) → done. done is status === "done", kept for older pages and agents.
export type Status = "new" | "progress" | "done";

export type Task = {
  id: string; list_id: string; title: string; status: Status; done: boolean;
  due_date: string | null; // a calendar day, "2026-10-17" (see due.ts)
  due_time: string | null; due_zone: string | null; // "15:00" in "America/New_York", with the date, or both null
  created_by: string | null; done_by: string | null; created_at: string; updated_at: string;
  pending?: boolean; // only on this device: a change not sent yet
};
export type TaskList = { id: string; name: string; owner: string | null; role: "owner" | "member"; members: string[]; tasks: Task[] };
export type ListInfo = Omit<TaskList, "tasks">; // what creating, renaming or adding a member answers
export type Snapshot = { me: string; lists: TaskList[] };

export type Me = { username: string };

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().then((json) => json?.detail, () => undefined);
    const message = typeof detail === "string" ? detail : `${method} ${path} failed (${response.status})`;
    throw new ApiError(response.status, message);
  }
  return (response.status === 204 ? null : await response.json()) as T;
}
