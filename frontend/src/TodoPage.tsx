// The whole list: loads it, and adds, ticks, renames and deletes todos through /api/todos.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Todo } from "./api";
import { isLoggedOut } from "./messages";
import { TodoItem } from "./TodoItem";

export type Change = (request: () => Promise<unknown>) => Promise<void>;

export function TodoPage({ onLoggedOut }: { onLoggedOut: () => void }) {
  const [todos, setTodos] = useState<Todo[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const titleInput = useRef<HTMLInputElement>(null);

  async function refresh() {
    try {
      setTodos(await api<Todo[]>("GET", "/api/todos"));
      setLoaded(true);
    } catch (e) {
      if (isLoggedOut(e)) return onLoggedOut();
      setError((e as Error).message);
    }
  }

  // Runs one change, then reloads the list, so the page always shows what the server has.
  const change: Change = async (request) => {
    try {
      await request();
      setError(null);
    } catch (e) {
      if (isLoggedOut(e)) return onLoggedOut();
      setError((e as Error).message);
    }
    await refresh();
  };

  useEffect(() => {
    void refresh();
  }, []);

  async function add(event: FormEvent) {
    event.preventDefault();
    const trimmed = title.trim();
    if (!trimmed) return;
    await change(() => api("POST", "/api/todos", { title: trimmed }));
    setTitle("");
    titleInput.current?.focus();
  }

  return (
    <main>
      <h1>Taskly</h1>

      <form onSubmit={add} autoComplete="off">
        <input
          ref={titleInput}
          name="title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={500}
          placeholder="What needs doing?"
          required
        />
        <button type="submit">Add</button>
      </form>

      {error && <p className="error" role="alert">{error}</p>}

      <ul>
        {todos.map((todo) => <TodoItem key={todo.id} todo={todo} change={change} />)}
      </ul>
      {loaded && todos.length === 0 && <p className="empty">Nothing to do. Add something above.</p>}
    </main>
  );
}
