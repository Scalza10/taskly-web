# Accounts, named lists and offline mode

Design, 2026-09-28. Status: approved in conversation, spec awaiting review.

## Goal

Taskly today is one shared list behind Caddy's `basic_auth`: one password for
everyone, no idea who did what, and no use without a connection. This design
turns it into:

- **Accounts.** Each person logs in with their own name and password. The app
  records who added and who ticked off each task.
- **Named lists.** Anyone can create lists and choose who is in each.
- **An installable, offline-capable web app** for phones and laptops. Tasks can
  be added, ticked, renamed and deleted offline and sync when back online.

### Decisions

| Question | Decision |
|---|---|
| Who sees which tasks | Several named lists, each with its own members |
| How accounts are made | The admin creates them with a command on the VM. No sign-up page |
| Rights inside a list | The owner (creator) renames, deletes and manages members. Members add, tick, edit and delete tasks, and can leave |
| Client | Installable web app (PWA). No native desktop app |
| Offline scope | Tasks fully offline. Lists and members need a connection |
| Sync approach | Queue local changes, send them in order, then download a full snapshot (below) |
| Frontend | React + Vite + TypeScript |

### Assumptions

- A small group (under ~20 people), lists of tens to hundreds of tasks. A full
  snapshot per sync is a few KB.
- Caddy's `basic_auth` is removed once the app has its own login. `/health`
  stays open.
- The existing todos move into a first list, "Taskly", and every active user
  becomes a member, so nobody loses what they see today.
- Two people changing the **same field** of the same task: the change that
  reaches the server last wins. Different fields don't clash.
- Server stays FastAPI + stdlib `sqlite3`, no ORM. All assets stay local: no CDNs.

### Success looks like

- You tick something off in a shop with no signal; it shows up for the others
  once your phone is back online.
- A lost phone can be signed out without changing anyone else's password.
- Nobody can see, or find out about, a list they aren't a member of.

## Sync approach

Considered:

- **A. Queue + full snapshot (chosen).** The device keeps the last full copy of
  everything the user can see, plus a queue of their unsent task changes. A sync
  sends the queue in order, then downloads `GET /api/sync` and replaces its copy.
  Deletions and other people's changes arrive for free, so the server needs no
  tombstones and no change log. Tasks get their IDs on the device, so a task
  created offline can be edited before it reaches the server.
- **B. Queue + incremental pull** ("changes since #N"). Scales further but needs
  tombstones, their cleanup and a change counter. We can move to it later
  without changing the queue.
- **C. A sync library** (PouchDB/CouchDB, Automerge). Handles conflicts well but
  replaces SQLite on the server and adds a large dependency.

## Data model

Two migrations are appended to `MIGRATIONS` in `db.py`, one per phase. The
existing migration 1 (`todos`) is not touched. Timestamps use the existing
format, `strftime('%Y-%m-%dT%H:%M:%SZ', 'now')`, set by the server; `DEFAULT (...)`
below stands for that expression.

### Migration 2 (phase 1: accounts)

```sql
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (...),
    disabled_at   TEXT
);
CREATE TABLE sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device       TEXT    NOT NULL DEFAULT '',
    created_at   TEXT    NOT NULL DEFAULT (...),
    last_used_at TEXT    NOT NULL DEFAULT (...)
);
ALTER TABLE todos ADD COLUMN created_by INTEGER REFERENCES users(id);
ALTER TABLE todos ADD COLUMN done_by    INTEGER REFERENCES users(id);
```

- Usernames are case-insensitive: `Maria` and `maria` are the same user.
- Users are disabled, never deleted, so attribution survives.
- Only the SHA-256 hash of a session token is stored: a copied database file
  can't be used to log in.
- `device` is a short label derived from the User-Agent ("Chrome on Android"),
  for telling sessions apart.

### Migration 3 (phase 2: lists)

```sql
CREATE TABLE lists (
    id         TEXT    PRIMARY KEY,               -- UUID, made by the server
    name       TEXT    NOT NULL,
    owner_id   INTEGER REFERENCES users(id),      -- NULL only for an unclaimed legacy list
    created_at TEXT    NOT NULL DEFAULT (...),
    updated_at TEXT    NOT NULL DEFAULT (...)
);
CREATE TABLE list_members (
    list_id   TEXT    NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    user_id   INTEGER NOT NULL REFERENCES users(id),
    joined_at TEXT    NOT NULL DEFAULT (...),
    PRIMARY KEY (list_id, user_id)
);
CREATE TABLE tasks (
    id         TEXT    PRIMARY KEY,               -- UUID, made by the device
    list_id    TEXT    NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    title      TEXT    NOT NULL,
    done       INTEGER NOT NULL DEFAULT 0,
    created_by INTEGER REFERENCES users(id),
    done_by    INTEGER REFERENCES users(id),
    created_at TEXT    NOT NULL DEFAULT (...),
    updated_at TEXT    NOT NULL DEFAULT (...)
);
CREATE INDEX tasks_list_id ON tasks(list_id);
```

- The owner also has a row in `list_members`, so "which lists can I see" is one
  lookup.
- IDs are UUID strings in the format `crypto.randomUUID()` produces.
- Deleting a list deletes its tasks. There is no trash.

The same migration moves the old data, then drops `todos`:

- Only if `todos` has rows: create a list "Taskly" with a UUID made in SQL from
  `randomblob`. Its owner is the active user with the lowest `id`, or NULL if
  there are no users.
- Every active user becomes a member of it.
- Every todo becomes a task with a new UUID, keeping `title`, `done`,
  `created_by`, `done_by`, `created_at` and `updated_at`.
- `DROP TABLE todos`.

An unowned legacy list is claimed by the first user created with
`taskly.admin add-user` (owner and member).

## Accounts and security

### Passwords

- Hashed with stdlib `hashlib.scrypt` (n=2^15, r=8, p=1, `maxmem` raised to fit),
  a random 16-byte salt per password, stored as `scrypt$n$r$p$salt_hex$hash_hex`
  so the parameters can be raised later without breaking old hashes.
- Compared with `hmac.compare_digest`.
- A login with an unknown username still hashes against a dummy value, so timing
  doesn't reveal which usernames exist.
- New passwords are at least 10 characters.

### Sessions

- Logging in makes a token with `secrets.token_urlsafe(32)`. The database keeps
  its SHA-256.
- Cookie `taskly_session`: `HttpOnly`, `SameSite=Lax`, `Path=/`,
  `Max-Age` 90 days. `Secure` when the request's scheme is `https`. Behind Caddy
  it always is (uvicorn already runs with `--proxy-headers`). Local
  `http://localhost` and tests get a cookie without `Secure`, so a local run
  still needs no `.env`.
- A session expires 90 days after its **last use** (sliding). `last_used_at` is
  written at most once an hour, and the cookie's `Max-Age` is refreshed then.
- Expired sessions are deleted on each login.

### Protecting the endpoints

- A FastAPI dependency, `CurrentUser`, reads the cookie, finds a live session of
  an active user, or answers **401**. Every `/api` route uses it except
  `/api/login`. `/health` and the static page are public: the page holds no data
  and must load offline.
- **Login throttling**, in memory: 10 failed attempts per username and 30 per
  client IP per 15 minutes, then **429** with `Retry-After`. The client IP is
  `request.client.host`, which is the real visitor because uvicorn trusts
  Caddy's forwarding headers and only Caddy can reach the app. The counters
  assume one uvicorn process (true today) and reset on deploy.
- **Cross-site writes:** `SameSite=Lax` keeps the cookie off other sites'
  requests. In addition, any non-GET `/api` request whose `Origin` header is
  present and doesn't match the request's own scheme and host is rejected with
  **403**. Requests without `Origin` (curl, tests) are allowed: they carry no
  browser cookies.

### Account endpoints

| Method and path | Body | Answer |
|---|---|---|
| `POST /api/login` | `{username, password}` | 204 and the cookie; 401 if wrong; 429 if throttled |
| `POST /api/logout` | | 204; deletes this session, clears the cookie. From phase 3 also `Clear-Site-Data: "cache", "storage"` |
| `GET /api/me` | | `{username}`, or 401 |
| `POST /api/me/password` | `{current, new}` | 204; 401 if `current` is wrong; 422 if `new` is too short. Deletes every other session of this user |

Changing your password is how you sign out a lost device yourself.

### Admin command

`python -m taskly.admin <command>`, on the VM through
`docker compose exec app python -m taskly.admin …` in `~/taskly`. It uses the
same `Settings` (so the same `DB_PATH`) and runs the migrations first.

| Command | Does |
|---|---|
| `add-user NAME` | Asks for the password twice (`getpass`). Empty: generates one with `secrets` and prints it. Claims an unowned legacy list |
| `reset-password NAME` | Same prompt; also deletes all of that user's sessions |
| `disable-user NAME` | Sets `disabled_at`, deletes their sessions. Each list they own passes to the active member who joined earliest; a list with no other active member keeps its owner |
| `enable-user NAME` | Clears `disabled_at` |
| `list-users` | Name, created, disabled, number of sessions |
| `revoke-sessions NAME` | Deletes all of that user's sessions |

Usernames are 2–32 characters: letters, digits, `.`, `_`, `-`.

## Lists, tasks and permissions

### Permission rules

- One helper answers "what is this user's role in list X": `owner`, `member` or
  none.
- **Not a member:** 404 for anything in or about that list, exactly as if it
  didn't exist. IDs can't be probed.
- **Member attempting an owner-only action:** 403.

### List endpoints (online only, even after phase 3)

| Method and path | Who | Answer |
|---|---|---|
| `POST /api/lists` `{name}` | anyone | 201 and the list; you are owner and member |
| `PATCH /api/lists/{id}` `{name}` | owner | The list |
| `DELETE /api/lists/{id}` | owner | 204; its tasks go too |
| `POST /api/lists/{id}/members` `{username}` | owner | 201 and the list; 200 if already a member; 404 if no such active user |
| `DELETE /api/lists/{id}/members/{username}` | owner, or that member themselves | 204. The owner can't remove themselves: 409 ("delete the list instead") |

List names are trimmed, 1–100 characters (422 otherwise).

### Task endpoints (what the offline queue replays; all retry-safe)

| Method and path | Body | Answer |
|---|---|---|
| `POST /api/tasks` | `{id, list_id, title}` | 201 and the task. `id` must be a UUID (422). Same `id` already in the same list: **200 and the existing task, unchanged** (a retry). Same `id` in another list: 409. Not a member of `list_id`: 404 |
| `PATCH /api/tasks/{id}` | `{title?, done?}` | The task. Only the fields sent change. `done: true` sets `done_by` to you, `done: false` clears it. 404 if gone or not a member |
| `DELETE /api/tasks/{id}` | | 204; 404 if gone or not a member |

Titles are trimmed, 1–500 characters, as today. The server sets `created_at`
and `updated_at` when a change arrives; device clocks are never used. Moving a
task between lists is not supported.

### Snapshot

`GET /api/sync` returns everything the user can see, in one response:

```json
{
  "me": "maria",
  "lists": [
    {
      "id": "…", "name": "Groceries", "owner": "maria", "role": "owner",
      "members": ["maria", "tom"],
      "tasks": [
        {"id": "…", "title": "Milk", "done": false, "created_by": "tom",
         "done_by": null, "created_at": "…", "updated_at": "…"}
      ]
    }
  ]
}
```

Users appear by username, never by internal id (`null` for legacy tasks with no
author). This is the only read endpoint for lists and tasks: there is no
separate `GET /api/lists`, since the page never needs lists without their tasks. Lists are sorted by name; tasks open first, then newest first
(`created_at DESC, id`). The phase 2 page already reads from this endpoint, so
phase 3 only adds storing it. `/api/todos` is removed in phase 2.

## Frontend

### Layout

```
frontend/
  package.json, package-lock.json, tsconfig.json, vite.config.ts, index.html
  src/
    main.tsx, App.tsx
    api.ts          fetch wrapper; types for every API answer
    store.ts        IndexedDB (via `idb`): stores `snapshot` and `queue`
    sync.ts         one sync at a time (below)
    view.ts         applyQueue(snapshot, queue): pure; what the screen shows
    components/     Login, ListPicker, TaskList, ListSettings, StatusLine
  public/           icons (PNG 192 and 512, maskable), made once from one SVG
taskly/static/      build output; gitignored
```

`store.ts`, `sync.ts` and `view.ts` don't import React. The UI reads them
through one hook.

### Phase 1 and 2 behaviour

- **1a:** the current page (add, tick, rename by clicking the title, delete,
  error line, empty state) rebuilt in React with the same behaviour and look.
- **1b:** a login screen shown on 401; a small account menu with the username,
  "Change password" and "Log out". Tasks show "added by …" and "done by …" in
  small text.
- **2:** a list picker at the top (the choice remembered per device in
  `localStorage`), "New list", and list settings: owners rename, manage members
  and delete; members see the members and can leave. After each change the page
  re-reads `/api/sync` and redraws, as today.
- It must work on a narrow phone screen throughout.

### Phase 3: offline

**What the screen shows** is `applyQueue(snapshot, queue)`: the last snapshot
with the unsent changes applied on top, tasks sorted as the server sorts them
(a task not yet on the server sorts as newest).

**Changing a task** appends `{method, path, body}` to the queue, redraws
immediately, and starts a sync. New tasks get their ID from
`crypto.randomUUID()`.

**Sync** (`sync.ts`), one at a time; a request for a sync while one runs makes
it run once more after:

1. Send queued changes in order. For each answer:
   - **2xx:** remove it from the queue.
   - **404, 409, 422:** remove it and add a note for the status line, e.g.
     "1 change couldn't be applied: the task was deleted".
   - **401:** stop; show the login screen; keep the queue.
   - **network error, 429, 5xx:** stop; keep the queue; try again on the next
     trigger.
2. `GET /api/sync` and store it as the snapshot, with the time.

Triggers: page open, after each local change, the `online` event, the tab
becoming visible, and every 30 seconds while visible.

**List and member actions** call the API directly. Offline, their buttons are
disabled with "needs a connection".

**Status line:** "Offline · 3 changes waiting", "Synced 2 min ago", and the
notes from failed changes.

**Logins with offline:**

- Opening the page shows the stored snapshot at once (works offline), then
  syncs. A first visit while offline shows "Connect once to log in."
- On 401 the login screen appears and the queue is kept. After logging in, if
  the username matches the snapshot's `me`, the queue is sent. If it's a
  **different** user, the snapshot and queue are deleted first.
- **Logging out needs a connection.** The cookie is `HttpOnly`, so only the
  server can end the session; an offline "log out" would leave it valid. If
  changes are waiting, the page first tries to send them, then asks
  "3 changes haven't synced. Log out anyway?". The server's answer carries
  `Clear-Site-Data`; the page also deletes its IndexedDB data and caches itself.

**What the device holds:** the snapshot and the queue, in the browser's
storage. The page never stores the password or the session token (the token is
in the browser's cookie store, unreadable by scripts). The device's lock and
disk encryption protect the data; anyone using an unlocked, logged-in device
sees that user's lists. Logging out removes them. Someone removed from a list
keeps their stale copy of it until the next sync; their queued changes to it
fail with 404 and are dropped.

**Service worker and manifest:** `vite-plugin-pwa`, `registerType: "autoUpdate"`.
It precaches the built files (hashed names), serves `index.html` for navigation
offline, and never handles `/api/*` or `/health`. After a deploy, devices take
the new version the next time they open the page. The manifest: name
"Taskly", `display: "standalone"`, `start_url: "/"`, `theme_color` and
`background_color` matching the page's own background, the icons above.

**Platform limits:** no Background Sync (Chromium only), so syncing happens
while Taskly is open. Safari may delete a site's storage after 7 days without
use unless it's installed to the home screen; the README tells iPhone users to
install it.

### Building and running

- **Dockerfile:** a first stage `node:22-slim` runs `npm ci && npm run build`;
  the Python stage copies the output into `taskly/static/`. The VM needs nothing
  new; `deploy.ps1` still ships `git archive` of the commit.
- **Local:** uvicorn as today, plus `npm run dev` (Vite, port 5173) which
  proxies `/api` and `/health` to port 8000. The proxy must keep the original
  `Host` header (no `changeOrigin`), or the Origin check rejects the page's own
  writes. To try install and offline locally: `npm run build`, then uvicorn
  alone on 8000.
- **`main.py`:** the static directory comes from `Settings` (default: the
  package's `static/`); `create_app` mounts it only if it exists, so the API
  runs without a build. Adds MIME type `application/manifest+json` for
  `.webmanifest`; keeps the `.js` fix.

## Deploying

### Changing the schema later

Migrations 2 and 3 can be edited freely until they are deployed. Once one has
run on the VM it is frozen: the database records its version and never runs it
again. Later changes are new migrations appended to `MIGRATIONS` (add a column
or table; for what SQLite can't alter in place, create a new table, copy, drop
the old one, as migration 3 does). Data a migration drops is gone, hence the
backups.

### Deploy steps (from phase 1a)

Today `docker compose up -d --build` stops the old container before the new one
migrates on startup, so a failing migration leaves the site down. `deploy.ps1`
changes to run these on the VM, in one `ssh` call, stopping at the first
failure:

1. **Build:** `docker compose build`. The old app keeps serving.
2. **Back up:** if the app container is running, SQLite's backup API inside it
   writes `/data/backups/taskly-<UTC timestamp>.db`; the newest 10 are kept.
3. **Migrate:** `docker compose run --rm --no-deps app python -m taskly.migrate`
   with the new image. It applies pending migrations and prints the version
   change (e.g. `schema 2 -> 3`, or `schema 3, nothing to do`). If it fails,
   the deploy stops: the old app keeps running and the database stays at its
   previous version, since each migration is one transaction.
4. **Start:** `docker compose up -d --remove-orphans`, then prune the replaced
   image, as today. The new app's startup migration finds nothing to do.
5. **Health check**, as today.

`taskly/migrate.py` is a small entry point around `db.migrate(Settings().db_path)`.
Startup keeps migrating too, so local runs and tests are unchanged.

Between steps 3 and 4 the old code runs briefly against the new schema. That is
harmless for migration 2 (added nullable columns). For migration 3 the old code
can't find `todos` for the few seconds until the new app is up; a request in
that window errors and a reload fixes it. Accepted for this app.

All of this touches only `~/taskly`. The backups matter because migration 3
drops `todos`: running older code again means restoring the backup taken before
that deploy.

Older code on a newer database: `migrate` runs `MIGRATIONS[user_version:]`, so
old code skips the migrations it doesn't know. After migration 2 the old code
still works (extra nullable columns on `todos`). After migration 3 it doesn't
(`todos` is gone), so rollback past phase 2 = restore the backup.

### Phase 1b rollout on the VM

1. Deploy. Caddy's password is still on, so for a few minutes people log in
   twice.
2. Create accounts: `docker compose exec app python -m taskly.admin add-user <name>`
   per person. Hand passwords over in person, not by chat.
3. Remove `@protected` and the `basic_auth` block from the site's Caddyfile
   block, leaving `reverse_proxy taskly:8000`. Validate and reload as in the
   README.
4. Check: a private browser window shows the app's login, no Caddy prompt.

Phases 2 and 3 are ordinary deploys.

## Testing

- **pytest** (fresh database per test, as now, through `make_settings`):
  - Migrations: start from a real version-1 database with todos (and one with
    none), check the resulting lists, members, tasks and attribution; check an
    unowned legacy list is claimed by `add-user`.
  - Accounts: hashing round-trip and parameter parsing; login, wrong password,
    unknown user; cookie flags over http and https; sliding expiry; disabled
    user; password change logs out other sessions; throttling and
    `Retry-After`; Origin check.
  - A permission table: each list and task endpoint × owner, member,
    non-member, logged out.
  - Retry-safety of `POST /api/tasks`; `/api/sync` shape and ordering.
  - The admin command's subcommands, including ownership transfer on disable.
  - `python -m taskly.migrate`: applies pending migrations and reports the
    version change; a second run reports nothing to do.
  - The page test uses a small stand-in static directory, not a build.
- **Vitest:** `applyQueue`; each sync outcome (2xx; 404/409/422; 401;
  network error; 429/5xx) with a fake `fetch` and an in-memory store;
  different-user login wipes local data.
- **In the browser**, after each phase: Claude drives the app locally
  (login, lists, offline via DevTools). The user checks install and offline on
  a real phone with a short checklist in the README.

## Phases

Each phase is deployed and usable on its own.

1. **React and accounts.**
   - 1a: React + TS port with the same behaviour; Docker Node stage;
     `deploy.ps1` builds, backs up, migrates, then starts (see "Deploy steps").
     README and CLAUDE.md: new commands, frontend rules, deploy steps.
   - 1b: migration 2, accounts, sessions, throttling, Origin check, admin
     command, login screen, account menu, attribution on todos. README: an
     "Accounts" section; the Caddy section loses its password how-to;
     CLAUDE.md: `basic_auth` is gone, the app owns login.
2. **Named lists.** Migration 3, list and task endpoints, permissions,
   `/api/sync`, list picker and settings; `/api/todos` removed. README API table.
3. **Offline.** `store`, `sync`, `view`, `vite-plugin-pwa`, status line,
   offline states, logout with `Clear-Site-Data`. README: installing on a phone;
   CLAUDE.md: "redraw from the local copy, then sync" replaces "reload from the
   server after every change".

## Out of scope

Sign-up and invite links; password reset by email; two-factor login; read-only
members; changing lists or members offline; moving tasks between lists; due
dates; notifications; trash or undo; background sync; a native desktop app; a
page listing your devices (changing your password signs the others out).

## Risks

- iPhone quirks with installed web apps: tested on a real phone in phase 3.
- Login throttling is per process: if the app ever runs more than one uvicorn
  worker, the counters move into the database.
- Migrations can't be undone: covered by the automatic pre-deploy backups, and
  a failing migration stops the deploy before the old app is replaced.
- A new npm toolchain: `package-lock.json` is committed and the Docker build
  uses `npm ci`, so builds are reproducible.
