// Talks to the FastAPI backend. JSON in and out; errors become ApiError with the HTTP status.

export type Task = {
  id: string; list_id: string; title: string; done: boolean;
  created_by: string | null; done_by: string | null; created_at: string; updated_at: string;
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
