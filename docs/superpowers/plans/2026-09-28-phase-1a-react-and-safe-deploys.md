# Phase 1a: React Page and Safe Deploys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild today's page in React + TypeScript with identical behaviour, build it in Docker, and make deploys build, back up, migrate and only then replace the running app.

**Architecture:** A new `frontend/` Vite project builds into `taskly/static/` (gitignored); FastAPI serves that folder when it exists, from a `STATIC_DIR` setting, so the API and its tests run without a build. Two small entry points, `taskly.backup` and `taskly.migrate`, run in throwaway containers of the new image from `deploy.ps1` before `docker compose up`.

**Tech Stack:** Python 3.12, FastAPI, stdlib `sqlite3`, pytest; Node ≥ 22.12, React 19, Vite 8, TypeScript 7, Vitest 5.

**Spec:** `docs/superpowers/specs/2026-09-28-accounts-lists-offline-design.md` (sections "Frontend → Layout, Building and running", "Deploying"). This is phase **1a** of 4; later plans: `2026-09-28-phase-1b-accounts.md`, `2026-09-28-phase-2-lists.md`, `2026-09-28-phase-3-offline.md`.

**Branch:** work on `phase-1a` off `main`; merge to `main` before deploying (the deploy ships `main`).

**Before starting:** the working tree must be clean. If `README.md` still has the uncommitted "clearer local run instructions" edit, commit it first (`docs: clearer local run instructions`).

## Global Constraints

- Only append to `MIGRATIONS`; never edit or reorder a deployed one. (No migration in this phase.)
- Keep all assets local: no CDNs or other sites.
- Node ≥ 22.12 locally (`"engines"` in `package.json`); Docker uses `node:22-slim`.
- `package-lock.json` is committed; Docker uses `npm ci`.
- `~/taskly` is the only thing a deploy touches. Never publish a port on `0.0.0.0`. Data lives only in `./data` (mounted at `/data`).
- `deploy.ps1` ships `git archive` of the commit; it sets TLS 1.2 explicitly.
- Commits: small, prefixed `feat:`, `fix:` or `docs:`, ending with the `Co-Authored-By` line from the session.
- Python tests: `.venv\Scripts\python.exe -m pytest`. Frontend tests: `npm --prefix frontend test`.

## Review Focus

1. **A fresh clone with no `npm run build`:** `uvicorn` must still start and `/health` answer; `/` is a 404, not a crash. (Task 1 test.)
2. **The very first deploy to a VM with no database file:** the backup step must skip cleanly, not fail the deploy. (Task 4 test.)
3. **Backup rotation:** with more than 10 backups, the oldest go and the newest 10 stay. (Task 4 test.)
4. **Migrate with nothing to do:** exit 0 and say so, so every ordinary deploy passes. (Task 4 test.)
5. **An API error the server explains:** the page shows the server's `detail` text when it is a string, not only "failed (422)". (Task 2 test.)

---

### Task 0: Update Node on the dev PC

Vite 8, `@vitejs/plugin-react` 6 and Vitest 5 need Node ≥ 22.12. The PC has 22.11.0.

- [ ] **Step 1: Install the current LTS**

Run (PowerShell): `winget install OpenJS.NodeJS.LTS`
Then open a new terminal.

- [ ] **Step 2: Check**

Run: `node --version`
Expected: `v22.12.0` or later (a `v24.x` LTS is fine).

No commit.

---

### Task 1: Serve the built page from a setting; tests stop depending on it

**Files:**
- Modify: `taskly/settings.py`
- Modify: `taskly/main.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_api.py` (replace `test_page_and_its_files_are_served`, add one test)

**Interfaces:**
- Produces: `Settings.static_dir: str` (env `STATIC_DIR`), default `str(Path(taskly/__file__).parent / "static")`. `create_app` mounts it at `/` only if it is a directory.
- Produces: `tests/conftest.py::make_settings(tmp_path, **overrides)` now also defaults `static_dir` to `tmp_path / "static"` (which doesn't exist unless a test creates it).

- [ ] **Step 1: Write the failing tests**

In `tests/test_api.py`, replace `test_page_and_its_files_are_served` with:

```python
def test_page_and_its_files_are_served(tmp_path):
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<!doctype html><title>Taskly</title>")
    (static / "assets").mkdir()
    (static / "assets" / "index-abc123.js").write_text("export {};")
    (static / "assets" / "index-abc123.css").write_text("body {}")

    with TestClient(create_app(make_settings(tmp_path, static_dir=str(static)))) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "<title>Taskly</title>" in page.text
        assert client.get("/assets/index-abc123.js").headers["content-type"].startswith("text/javascript")
        assert client.get("/assets/index-abc123.css").headers["content-type"].startswith("text/css")


def test_api_runs_without_a_built_page(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 404
```

and add at the top of the file:

```python
from conftest import make_settings
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_api.py -k "page or without" -v`
Expected: both FAIL. `Settings` has no `static_dir` field yet and ignores unknown values (`extra="ignore"`), so the app still serves the package's `static/`: `/assets/index-abc123.js` is a 404 in the first test, and `/` is a 200 instead of a 404 in the second.

- [ ] **Step 3: Add the setting**

`taskly/settings.py`:

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Where `npm run build` in frontend/ writes the page. Not in git.
PACKAGE_STATIC = Path(__file__).parent / "static"


class Settings(BaseSettings):
    """Read from the environment and `.env` in the working directory."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # The SQLite file. docker-compose.yml sets it to /data/taskly.db, on the mounted volume.
    db_path: str = "./data/taskly.db"

    # The built page. If the folder doesn't exist (no build yet), the API runs without a page.
    static_dir: str = str(PACKAGE_STATIC)
```

- [ ] **Step 4: Mount it only if it exists**

`taskly/main.py`, replace everything below the imports with:

```python
# On Windows, mimetypes reads .js from the registry, which can say text/plain;
# browsers then refuse to run the page's module script.
mimetypes.add_type("text/javascript", ".js")


def create_app(settings: Settings | None = None) -> FastAPI:
    """App factory: uvicorn runs it with --factory, tests pass their own Settings."""
    settings = settings or Settings()
    db.migrate(settings.db_path)

    app = FastAPI(title="Taskly")
    app.state.settings = settings
    app.include_router(routes.router)
    # Last, so the API routes above win. html=True serves index.html at /.
    # No folder means no build yet (frontend/, npm run build): the API still works.
    static = Path(settings.static_dir)
    if static.is_dir():
        app.mount("/", StaticFiles(directory=static, html=True), name="static")
    return app
```

and remove the now-unused `STATIC_DIR = Path(__file__).parent / "static"` line (keep `from pathlib import Path`).

- [ ] **Step 5: Keep tests off the package folder**

`tests/conftest.py`, replace `make_settings`:

```python
def make_settings(tmp_path, **overrides) -> Settings:
    """Settings on a fresh database in tmp_path. _env_file=None keeps a local .env out of tests.
    static_dir points at tmp_path/static, which exists only if a test creates it."""
    values = {"db_path": str(tmp_path / "taskly.db"), "static_dir": str(tmp_path / "static")}
    return Settings(_env_file=None, **{**values, **overrides})
```

- [ ] **Step 6: Run all Python tests**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass (15 tests).

- [ ] **Step 7: Commit**

```bash
git add taskly/settings.py taskly/main.py tests/conftest.py tests/test_api.py
git commit -m "feat: serve the page from STATIC_DIR, only if it has been built"
```

---

### Task 2: The React + TypeScript page, same behaviour as today

**Files:**
- Create: `frontend/package.json` (via npm), `frontend/package-lock.json` (via npm)
- Create: `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`
- Create: `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/TodoPage.tsx`, `frontend/src/TodoItem.tsx`, `frontend/src/api.ts`, `frontend/src/style.css`
- Test: `frontend/src/api.test.ts`
- Delete: `taskly/static/index.html`, `taskly/static/app.js`, `taskly/static/style.css`
- Modify: `.gitignore`

**Interfaces:**
- Produces (`frontend/src/api.ts`):
  - `class ApiError extends Error { readonly status: number }`
  - `api<T = unknown>(method: string, path: string, body?: unknown): Promise<T>`: JSON in and out; resolves `null` for 204; throws `ApiError` with the server's string `detail` as message when there is one, else `"<METHOD> <path> failed (<status>)"`. Network failures reject with the browser's `TypeError` unchanged.
  - `type Todo = { id: number; title: string; done: boolean; created_at: string; updated_at: string }`
- Produces (`frontend/src/TodoPage.tsx`): `TodoPage(): JSX.Element`, the whole list UI. `App.tsx` renders it; phase 1b puts the login decision in `App`.
- Build output: `taskly/static/index.html` + `taskly/static/assets/*`.

- [ ] **Step 1: Create the project and install**

```powershell
New-Item -ItemType Directory -Force frontend | Out-Null
Set-Content -Encoding utf8 frontend/package.json @'
{
  "name": "taskly-frontend",
  "private": true,
  "type": "module",
  "engines": { "node": ">=22.12" },
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "typecheck": "tsc",
    "test": "vitest run"
  }
}
'@
npm --prefix frontend install react react-dom
npm --prefix frontend install -D vite @vitejs/plugin-react typescript vitest @types/react @types/react-dom
```

Expected: `frontend/node_modules/` and `frontend/package-lock.json` exist; `package.json` gains `dependencies` and `devDependencies`.

- [ ] **Step 2: Config files**

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noEmit": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`frontend/vite.config.ts`:

```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// npm run dev serves the page on 5173 and sends API calls to uvicorn on 8000.
// No changeOrigin: the Host header must stay localhost:5173, because from phase 1b
// the API refuses writes whose Origin doesn't match the Host.
const backend = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../taskly/static", emptyOutDir: true },
  server: { port: 5173, strictPort: true, proxy: { "/api": backend, "/health": backend } },
  test: { environment: "node" },
});
```

`frontend/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Taskly</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

`.gitignore`, add under `# Local settings and data`:

```
# The frontend's packages and its build (made by npm run build or the Docker build)
frontend/node_modules/
taskly/static/
```

- [ ] **Step 3: Write the failing test for `api`**

`frontend/src/api.test.ts`:

```ts
import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

function answer(status: number, body?: unknown) {
  const fetch = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

test("sends JSON and returns the parsed answer", async () => {
  const fetch = answer(201, { id: 1 });
  expect(await api("POST", "/api/todos", { title: "x" })).toEqual({ id: 1 });
  expect(fetch).toHaveBeenCalledWith("/api/todos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: '{"title":"x"}',
  });
});

test("a request without a body sends no Content-Type", async () => {
  const fetch = answer(200, []);
  await api("GET", "/api/todos");
  expect(fetch).toHaveBeenCalledWith("/api/todos", { method: "GET", headers: {}, body: undefined });
});

test("204 resolves to null", async () => {
  answer(204);
  expect(await api("DELETE", "/api/todos/1")).toBeNull();
});

test("an error uses the server's detail when it is text", async () => {
  answer(404, { detail: "No such todo" });
  const error = await api("PATCH", "/api/todos/9", { done: true }).catch((e) => e);
  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(404);
  expect(error.message).toBe("No such todo");
});

test("an error without a text detail says what failed", async () => {
  answer(422, { detail: [{ msg: "too long" }] });
  const error = await api("POST", "/api/todos", { title: "x" }).catch((e) => e);
  expect(error.message).toBe("POST /api/todos failed (422)");
});
```

- [ ] **Step 4: Run it to see it fail**

Run: `npm --prefix frontend test`
Expected: FAIL, `Failed to resolve import "./api"`.

- [ ] **Step 5: Write `api.ts`**

`frontend/src/api.ts`:

```ts
// Talks to the FastAPI backend. JSON in and out; errors become ApiError with the HTTP status.

export type Todo = {
  id: number;
  title: string;
  done: boolean;
  created_at: string;
  updated_at: string;
};

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
```

- [ ] **Step 6: Run the test to see it pass**

Run: `npm --prefix frontend test`
Expected: PASS, 5 tests.

- [ ] **Step 7: The page**

`frontend/src/style.css`: copy `taskly/static/style.css` exactly, then append:

```css
/* The rename field replaces the title while editing. */
input.title {
  padding: 0;
  border: 0;
  border-bottom: 1px solid var(--accent);
  background: none;
  color: inherit;
  font: inherit;
}
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "./style.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx`:

```tsx
import { TodoPage } from "./TodoPage";

export function App() {
  return <TodoPage />;
}
```

`frontend/src/TodoPage.tsx`:

```tsx
// The whole list: loads it, and adds, ticks, renames and deletes todos through /api/todos.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Todo } from "./api";
import { TodoItem } from "./TodoItem";

export type Change = (request: () => Promise<unknown>) => Promise<void>;

export function TodoPage() {
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
      setError((e as Error).message);
    }
  }

  // Runs one change, then reloads the list, so the page always shows what the server has.
  const change: Change = async (request) => {
    try {
      await request();
      setError(null);
    } catch (e) {
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
```

`frontend/src/TodoItem.tsx`:

```tsx
// One todo: tick it, click the title to rename (Enter or leaving the field saves, Escape cancels), × deletes.
import { useRef, useState, type FocusEvent, type KeyboardEvent } from "react";
import { api, type Todo } from "./api";
import type { Change } from "./TodoPage";

export function TodoItem({ todo, change }: { todo: Todo; change: Change }) {
  const [editing, setEditing] = useState(false);
  const cancelled = useRef(false);
  const path = `/api/todos/${todo.id}`;

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") event.currentTarget.blur();
    if (event.key === "Escape") {
      cancelled.current = true;
      event.currentTarget.blur();
    }
  }

  function onBlur(event: FocusEvent<HTMLInputElement>) {
    setEditing(false);
    if (cancelled.current) {
      cancelled.current = false;
      return;
    }
    const newTitle = event.currentTarget.value.trim();
    if (newTitle && newTitle !== todo.title) void change(() => api("PATCH", path, { title: newTitle }));
  }

  return (
    <li className={todo.done ? "done" : undefined}>
      <input
        type="checkbox"
        checked={todo.done}
        aria-label="done"
        onChange={(e) => {
          const done = e.target.checked;
          void change(() => api("PATCH", path, { done }));
        }}
      />
      {editing ? (
        <input
          className="title"
          aria-label="title"
          defaultValue={todo.title}
          maxLength={500}
          autoFocus
          onKeyDown={onKeyDown}
          onBlur={onBlur}
        />
      ) : (
        <span className="title" onClick={() => setEditing(true)}>{todo.title}</span>
      )}
      <button className="delete" aria-label={`delete "${todo.title}"`} onClick={() => void change(() => api("DELETE", path))}>
        ×
      </button>
    </li>
  );
}
```

- [ ] **Step 8: Remove the old page and build the new one**

```powershell
git rm taskly/static/index.html taskly/static/app.js taskly/static/style.css
npm --prefix frontend run build
```

Expected: `tsc` prints nothing; Vite prints `../taskly/static/index.html` and `../taskly/static/assets/index-<hash>.js` / `.css`.

- [ ] **Step 9: Check it in the browser, like a user**

Run uvicorn (`.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload`) and open <http://localhost:8000/>. Check, one by one:
- The list from `data/taskly.db` shows, open ones first.
- Add "React works" with Enter; the field clears and keeps focus. Add another with the button.
- Tick one: it moves below the open ones, crossed out.
- Click a title, change it, press Enter: renamed. Click again, type, press Escape: unchanged. Click, clear it, click away: unchanged.
- × deletes. With none left: "Nothing to do. Add something above."
- Narrow the window to phone width (DevTools, 375 px): no horizontal scrolling.
- DevTools console: no errors.

Then run `npm --prefix frontend run dev` and open <http://localhost:5173/>: same list (through the proxy), and editing `TodoPage.tsx` reloads instantly.

- [ ] **Step 10: Run all tests**

Run: `.venv\Scripts\python.exe -m pytest -q` and `npm --prefix frontend test`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add .gitignore frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html frontend/src
git commit -m "feat: the page in React and TypeScript, same behaviour"
```

(The `git rm` from Step 8 is already staged and goes into this commit.)

---

### Task 3: Build the page in Docker

**Files:**
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Modify: `docker-compose.yml`

**Interfaces:**
- Produces: the image is tagged `taskly-app` (explicit `image:` in compose). Task 4's deploy runs `docker run … taskly-app python -m taskly.<module>`.

- [ ] **Step 1: Dockerfile with a Node stage**

Replace the top of `Dockerfile` (everything before `EXPOSE 8000`) with:

```dockerfile
# The page (frontend/): React + TypeScript, built to static files.
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts writes to ../taskly/static, i.e. /build/taskly/static.
RUN npm run build

FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY taskly ./taskly
COPY --from=frontend /build/taskly/static ./taskly/static

RUN mkdir -p /data
ENV DB_PATH=/data/taskly.db \
    PYTHONUNBUFFERED=1
```

(Keep `EXPOSE`, `HEALTHCHECK` and `CMD` below as they are.)

- [ ] **Step 2: Keep local builds out of the context**

`.dockerignore`, append:

```
frontend/node_modules
taskly/static
```

- [ ] **Step 3: Name the image**

`docker-compose.yml`, under `app:` add `image: taskly-app` right after `build: .`, with a comment:

```yaml
    build: .
    # deploy.ps1 runs backups and migrations in throwaway containers of this image.
    image: taskly-app
```

- [ ] **Step 4: Build and run it locally**

```powershell
docker network create web   # only if it doesn't exist yet; an "already exists" error is fine
docker compose up -d --build
curl.exe -s http://localhost:8001/health
curl.exe -s -o NUL -w "%{http_code} %{content_type}\n" http://localhost:8001/
```

Expected: `{"status":"ok"}`, then `200 text/html; charset=utf-8`. Open <http://localhost:8001/> and add/tick/delete one todo. Then `docker compose down`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore docker-compose.yml
git commit -m "feat: build the React page in the Docker image"
```

---

### Task 4: Backup and migrate entry points

**Files:**
- Create: `taskly/backup.py`
- Create: `taskly/migrate.py`
- Modify: `taskly/db.py` (add `current_version`)
- Test: `tests/test_backup.py`, `tests/test_migrate.py`

**Interfaces:**
- Produces: `db.current_version(path: str) -> int`: 0 if the file doesn't exist; never creates it.
- Produces: `backup.backup(path: str, keep: int = 10, now: datetime | None = None) -> Path | None`: writes `<db folder>/backups/<stem>-YYYYMMDDTHHMMSSZ.db` with SQLite's backup API; deletes all but the newest `keep`; `None` if the database doesn't exist.
- Produces: `migrate.run(path: str) -> str`: applies pending migrations; returns `"schema A -> B"` or `"schema B, nothing to do"`.
- Produces: `python -m taskly.backup` and `python -m taskly.migrate`, both using `Settings().db_path`, printing one line, exit 0 (an exception exits non-zero).

- [ ] **Step 1: Write the failing tests**

`tests/test_backup.py`:

```python
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone

from taskly import backup, db


def test_no_database_means_nothing_to_back_up(tmp_path):
    assert backup.backup(str(tmp_path / "taskly.db")) is None
    assert not (tmp_path / "backups").exists()


def test_backup_is_a_full_copy(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("INSERT INTO todos (title) VALUES ('keep me')")

    target = backup.backup(path, now=datetime(2026, 9, 28, 12, 0, 0, tzinfo=timezone.utc))

    assert target == tmp_path / "backups" / "taskly-20260928T120000Z.db"
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT title FROM todos").fetchall() == [("keep me",)]
        assert copy.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)


def test_only_the_newest_backups_are_kept(tmp_path):
    path = str(tmp_path / "taskly.db")
    db.migrate(path)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for day in range(12):
        backup.backup(path, keep=10, now=start + timedelta(days=day))

    names = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(names) == 10
    assert names[0] == "taskly-20260103T000000Z.db"
    assert names[-1] == "taskly-20260112T000000Z.db"
```

`tests/test_migrate.py`:

```python
from taskly import db, migrate


def test_first_run_creates_the_schema(tmp_path):
    path = str(tmp_path / "taskly.db")
    assert db.current_version(path) == 0
    assert migrate.run(path) == f"schema 0 -> {len(db.MIGRATIONS)}"


def test_second_run_has_nothing_to_do(tmp_path):
    path = str(tmp_path / "taskly.db")
    migrate.run(path)
    assert migrate.run(path) == f"schema {len(db.MIGRATIONS)}, nothing to do"


def test_current_version_does_not_create_the_file(tmp_path):
    path = tmp_path / "taskly.db"
    assert db.current_version(str(path)) == 0
    assert not path.exists()
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_backup.py tests/test_migrate.py -v`
Expected: FAIL, `ImportError: cannot import name 'backup' from 'taskly'`.

- [ ] **Step 3: `db.current_version`**

`taskly/db.py`, add after `migrate`:

```python
def current_version(path: str) -> int:
    """The schema version of the file, 0 if there is no file yet. Never creates it."""
    if not Path(path).exists():
        return 0
    with closing(connect(path)) as conn:
        return conn.execute("PRAGMA user_version").fetchone()[0]
```

- [ ] **Step 4: `taskly/backup.py`**

```python
"""`python -m taskly.backup`: copy the database into backups/ next to it; keep the newest ten.

deploy.ps1 runs it before migrating. SQLite's backup API makes a consistent copy while the app runs."""

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .settings import Settings

KEEP = 10


def backup(path: str, keep: int = KEEP, now: datetime | None = None) -> Path | None:
    source = Path(path)
    if not source.exists():
        return None
    folder = source.parent / "backups"
    folder.mkdir(exist_ok=True)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{source.stem}-{stamp}.db"
    with closing(sqlite3.connect(source)) as src, closing(sqlite3.connect(target)) as dst:
        src.backup(dst)
    # The names sort by time, oldest first.
    for old in sorted(folder.glob(f"{source.stem}-*.db"))[:-keep]:
        old.unlink()
    return target


def main() -> None:
    target = backup(Settings().db_path)
    print(f"backed up to {target}" if target else "no database yet, nothing to back up")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: `taskly/migrate.py`**

```python
"""`python -m taskly.migrate`: apply pending schema migrations and say what changed.

deploy.ps1 runs it with the new image before starting the new app, so a failing migration
stops the deploy while the old app keeps running. The app also migrates on startup."""

from . import db
from .settings import Settings


def run(path: str) -> str:
    before = db.current_version(path)
    after = db.migrate(path)
    return f"schema {before} -> {after}" if after != before else f"schema {after}, nothing to do"


def main() -> None:
    print(run(Settings().db_path))


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the tests to see them pass**

Run: `.venv\Scripts\python.exe -m pytest -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add taskly/db.py taskly/backup.py taskly/migrate.py tests/test_backup.py tests/test_migrate.py
git commit -m "feat: backup and migrate commands for the deploy"
```

---

### Task 5: Deploy builds, backs up, migrates, then starts

**Files:**
- Modify: `scripts/deploy.ps1`

**Interfaces:**
- Consumes: image `taskly-app` (Task 3); `python -m taskly.backup`, `python -m taskly.migrate` (Task 4).

- [ ] **Step 1: Update the header comment**

In the `<# … #>` block of `scripts/deploy.ps1`, replace the line
`Only ~/taskly on the VM changes. Caddy (~/proxy), Reels and any other app keep running,`
and the line after it with:

```
On the VM it builds the new image while the old app keeps serving, backs up the database
(~/taskly/data/backups, newest 10), migrates it with the new image, and only then replaces
the app. A failing build or migration stops there: the old app keeps running.
Only ~/taskly on the VM changes. Caddy (~/proxy), Reels and any other app keep running,
and ~/taskly/.env is never touched.
```

- [ ] **Step 2: Replace the VM step**

Replace the whole `Invoke-Native "Rebuilding and restarting on the VM, then removing the old image" { … }` block, including its comment, with:

```powershell
    # One ssh call (one passphrase prompt), stopping at the first failure:
    # - the "web" network is shared with Caddy and the other apps; created if missing,
    #   since compose won't start without it;
    # - build while the old app keeps serving;
    # - backup and migrate run in throwaway containers of the new image, with no network
    #   (a compose one-off container would join "web" as "taskly" and could get Caddy's traffic);
    # - up replaces the app; --remove-orphans deletes containers of services no longer in
    #   docker-compose.yml; the prune removes only untagged images nothing uses: the one replaced.
    $steps = @(
        "mkdir -p ~/taskly", "cd ~/taskly",
        "tar -xzf ~/taskly.tar.gz", "rm ~/taskly.tar.gz",
        "(docker network inspect web >/dev/null 2>&1 || docker network create web)",
        "docker compose build",
        "docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.backup",
        "docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.migrate",
        "docker compose up -d --remove-orphans",
        "docker image prune -f"
    ) -join " && "
    Invoke-Native "Building, backing up, migrating and restarting on the VM" {
        ssh -i $keyFile $target $steps
    }
```

- [ ] **Step 3: Check the script parses and the command reads right**

Run:

```powershell
$tokens = $errors = $null; $null = [System.Management.Automation.Language.Parser]::ParseFile("$PWD\scripts\deploy.ps1", [ref]$tokens, [ref]$errors); $errors
```

Expected: no output (no parse errors).

Then check the `docker run` lines by hand against the running local stack (Task 3):

```powershell
docker compose build
docker run --rm --network none -v "${PWD}\data:/data" taskly-app python -m taskly.backup
docker run --rm --network none -v "${PWD}\data:/data" taskly-app python -m taskly.migrate
```

Expected: `backed up to /data/backups/taskly-<stamp>.db`, then `schema 1, nothing to do`; `data\backups\` now holds one file.

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy.ps1
git commit -m "feat: deploys back up and migrate before replacing the app"
```

---

### Task 6: README and CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: README, "Run it locally"**

Replace the **With Python** part (up to, not including, **With Docker**) with:

````markdown
**With Python and Node** (Python 3.12, Node 22.12 or newer), from the repo folder.
Once, and when requirements change:

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements-dev.txt
npm --prefix frontend install
```

Then, in two terminals:

```powershell
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # the API, port 8000
npm --prefix frontend run dev                                                    # the page, port 5173
```

Open <http://localhost:5173/>. Saving a file in `frontend/src` updates the page
at once; `--reload` restarts the API when you save a Python file. Stop either
with Ctrl+C. macOS or Linux: `.venv/bin/pip` and `.venv/bin/python`.

To see the page exactly as deployed, build it (`npm --prefix frontend run build`,
into `taskly/static/`) and open uvicorn's own <http://localhost:8000/>. Without a
build, port 8000 has only the API.

The database is created at `./data/taskly.db` and survives restarts; delete the
file to start empty. No `.env` is needed; copy `.env.example` to `.env` only to
put the database somewhere else (`DB_PATH`).
````

and replace the **Tests:** paragraph with:

```markdown
**Tests:** `.venv\Scripts\python.exe -m pytest` for the API (under a second;
each test gets its own database, so your local data is untouched) and
`npm --prefix frontend test` for the page's logic.
```

- [ ] **Step 2: README, "Layout"**

Replace the code block with:

````markdown
```
taskly/
  main.py       create_app(): runs the migrations, adds the routes, serves the built page
  settings.py   Settings (DB_PATH, STATIC_DIR), read from the environment and .env
  db.py         the SQLite connection and the schema migrations
  todos.py      the queries
  routes.py     the HTTP endpoints
  backup.py     python -m taskly.backup: copy the database to data/backups/
  migrate.py    python -m taskly.migrate: apply pending migrations
  static/       the built page (not in git)
frontend/
  src/          the page: React + TypeScript (api.ts talks to the API)
  vite.config.ts
tests/
scripts/deploy.ps1
```
````

- [ ] **Step 3: README, backups and restoring**

In "## The database", replace the **Backup** paragraph and its code block with:

````markdown
**Backups.** Every deploy copies the database to
`~/taskly/data/backups/taskly-<UTC time>.db` before migrating, and keeps the
newest 10. To make one by hand (safe while the app runs):

```bash
cd ~/taskly
docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.backup
```

**Restoring a backup** (for example to go back to code from before a migration
that removed something):

```bash
cd ~/taskly
docker compose stop app
cp data/taskly.db data/taskly-before-restore.db
cp data/backups/taskly-<time>.db data/taskly.db
rm -f data/taskly.db-wal data/taskly.db-shm     # stale journal files would corrupt the restored copy
docker compose start app
```

Then deploy the code that matches that backup.
````

- [ ] **Step 4: README, "Deploying"**

Replace the paragraph starting "It ships the last **commit**" with:

```markdown
It ships the last **commit** on `main` (`git archive`, so uncommitted changes
stay behind) and unpacks it into `~/taskly`. Then, on the VM: it builds the new
image while the old app keeps serving, backs up the database, runs the pending
migrations with the new image, and only then replaces the app, deletes the image
it replaced, and waits up to a minute for `https://<site>/health`. If the build
or a migration fails, it stops there and the old app keeps running on the
unchanged database. `-Branch` deploys another branch; `-Config` points at
another settings file.
```

- [ ] **Step 5: CLAUDE.md**

Apply these edits:

In "## Commands", replace the block with:

````markdown
```powershell
.venv\Scripts\python.exe -m pytest                                   # API tests, under a second
.venv\Scripts\python.exe -m pytest tests/test_api.py::test_delete    # one test
npm --prefix frontend test                                           # page logic tests (Vitest)
npm --prefix frontend run build                                      # typecheck + build into taskly/static/
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # API on :8000, reads .env
npm --prefix frontend run dev                                        # page on :5173, proxies /api to :8000
docker compose up -d --build                                         # http://localhost:8001; needs `docker network create web` once
.\scripts\deploy.ps1                                                 # deploy the last commit on main
```

Node ≥ 22.12. No linter or formatter is configured.
````

(and delete the old separate "No linter or formatter is configured." line).

In "## Architecture", replace the **App factory** and **Frontend** bullets with:

```markdown
- **App factory.** `create_app(settings=None)` in `main.py` runs `db.migrate`, adds `routes.router`, and mounts `settings.static_dir` at `/` last (so API routes win; `html=True` serves `index.html`), only if that folder exists: without a build the API still runs. Tests pass their own `Settings`; `make_settings` points `static_dir` at an empty tmp folder.
- **Frontend** (`frontend/`). React + TypeScript, built by Vite into `taskly/static/` (gitignored; the Docker image builds it in a Node stage). `src/api.ts` is the only place that calls `fetch`; it throws `ApiError` with the server's `detail`. After every change the page reloads the list from the server rather than patching state. Keep all assets local: no CDNs or other sites. The dev server's proxy must not use `changeOrigin`.
```

In "## Deployment (shared VM)", replace the **`deploy.ps1` ships the last commit** bullet with:

```markdown
- **`deploy.ps1` ships the last commit via `git archive`**, not the working tree. On the VM it builds, backs up (`python -m taskly.backup`), migrates (`python -m taskly.migrate`), then runs `docker compose up`. Backup and migrate run as `docker run --rm --network none … taskly-app`, never `docker compose run`: a compose one-off container joins `web` with alias `taskly` and could receive Caddy's traffic. It sets TLS 1.2 explicitly because Windows PowerShell 5.1 doesn't offer it by default.
```

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: React page, backups and the new deploy steps"
```

---

### Task 7: Deploy phase 1a

- [ ] **Step 1:** Merge `phase-1a` into `main` (fast-forward), run both test suites on `main`.
- [ ] **Step 2:** `.\scripts\deploy.ps1`. Expected in the output: `backed up to /data/backups/…`, `schema 1, nothing to do`, then `Deployed. status=ok`.
- [ ] **Step 3:** Open `https://<site>/`, log in through Caddy as before, and repeat the checks from Task 2 Step 9 on a phone.
