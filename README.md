# Taskly

A small shared to-do app with named lists: a FastAPI app with a SQLite database and a React +
TypeScript page. It runs in Docker on the same VM as Reels, behind the same
Caddy, on its own host name. AI agents (Claude, Gemini) can connect to it as you
and work with your lists ([Talking to it from Claude](#talking-to-it-from-claude-mcp)).

## Run it locally

**With Python and Node** (Python 3.12, Node 22.12 or newer), from the repo folder.
Once, and when requirements change:

```powershell
python -m venv .venv
.venv\Scripts\pip.exe install -r requirements-dev.txt
npm --prefix frontend ci
```

Then, in two terminals:

```powershell
.venv\Scripts\python.exe -m uvicorn taskly.main:create_app --factory --reload   # the API, port 8000
npm --prefix frontend run dev                                                    # the page, port 5173
```

Open <http://localhost:5173/>. The page asks you to log in, so create yourself
an account once (see [Accounts](#accounts)). Saving a file in `frontend/src` updates the page
at once; `--reload` restarts the API when you save a Python file. Stop either
with Ctrl+C. macOS or Linux: `.venv/bin/pip` and `.venv/bin/python`.

To see the page exactly as deployed, build it (`npm --prefix frontend run build`,
into `taskly/static/`) and open uvicorn's own <http://localhost:8000/>. Without a
build, port 8000 has only the API.

The service worker (offline and install) only runs on the build: use
`npm --prefix frontend run build` and uvicorn's <http://localhost:8000/> to try
them, with DevTools → Network → Offline. Opening the dev server from a phone on
your network (`http://<pc-ip>:5173`) doesn't work: adding tasks needs
`crypto.randomUUID()`, which browsers only offer on https or localhost.

The database is created at `./data/taskly.db` and survives restarts; delete the
file to start empty. No `.env` is needed; copy `.env.example` to `.env` only to
put the database somewhere else (`DB_PATH`).

**With Docker** (the same container as on the VM):

```bash
docker network create web      # once; the compose file expects it (it's how Caddy reaches the app on the VM)
docker compose up -d --build
```

Open <http://localhost:8001/>. The database is `./data/taskly.db` on your
machine, mounted into the container. Create an account first
(`docker compose exec app python -m taskly.admin add-user me`).

**Tests:** `.venv\Scripts\python.exe -m pytest` for the API (under a second;
each test gets its own database, so your local data is untouched) and
`npm --prefix frontend test` for the page's logic.

## API

| Method and path | Body | Answer |
|---|---|---|
| `GET /health` | | `{"status": "ok"}`; also checks the database |
| `POST /api/login` | `{"username", "password"}` | 204 and the session cookie; 401 if wrong; 429 after too many tries |
| `POST /api/logout` | | 204; ends this device's session and tells the browser to clear the site's saved data (`Clear-Site-Data: "storage"`) |
| `GET /api/me` | | `{"username"}` |
| `POST /api/me/password` | `{"current", "new"}` | 204; logs out your other devices. 403 if `current` is wrong, 422 if `new` is under 6 characters |
| `GET /api/sync` | | Everything you can see: `{"me", "lists": [{"id", "name", "owner", "role", "members", "tasks": [...]}]}`, lists by name, tasks not done first (in progress too), then the ones with a due date, soonest first (a date alone counts as the end of that day, in UTC; the page sorts by its own time zone), then oldest first |
| `POST /api/lists` | `{"name": "Groceries"}` | 201 and the list; you own it |
| `PATCH /api/lists/{id}` | `{"name": ...}` | The list. Owner only |
| `DELETE /api/lists/{id}` | | 204; its tasks go too. Owner only |
| `POST /api/lists/{id}/members` | `{"username": "tom"}` | 201 (200 if already in). Owner only; 404 for a name that is unknown or disabled |
| `DELETE /api/lists/{id}/members/{username}` | | 204. The owner removes anyone; anyone can remove themselves (leave), except the owner (409) |
| `POST /api/tasks` | `{"id": "<uuid>", "list_id": "<uuid>", "title": "Milk"}`, optionally `"notes": "The oat one"` and `"due_date": "2026-10-17"`, and with it `"due_time": "15:00", "due_zone": "America/New_York"` and `"repeat": "FREQ=WEEKLY;BYDAY=MO"` | 201 and the task. The same `id` again in the same list: 200 and the stored task (a safe retry). The same `id` in another list: 409 |
| `PATCH /api/tasks/{id}` | Any of `{"title", "status", "done", "due_date", "notes", "repeat"}`, and with `due_date` its `"due_time"` and `"due_zone"`; finishing a repeating task, `"next_id"` and `"finished_on"` | The task. `status` is `"new"`, `"progress"` or `"done"` (anything else: 422). `done: true` is status done; `done: false` reopens a done task as new and leaves one in progress alone. `status` wins if both are sent. Finishing records you as `done_by`; any other status clears it. `due_date` replaces the due date as a whole: its time too, so a `due_date` without `due_time` has no time, and `due_date: null` removes it; left out, it all stays. `due_time` and `due_zone` come together, only with `due_date` (422 otherwise). `notes` replaces the notes; `null` or `""` removes them; left out, they stay. `repeat` replaces the rule (it needs a due date, else 422), `null` or `""` stops it, and removing the due date does too; a `due_date` alone moves a rule taken from the old date (every week on its weekday) with it. Finishing a repeating task makes the next one, which takes the rule over; `next_id` is its id (made by the page; another task's: 409, and nothing changes) and `finished_on` the day it was finished there; left out, a new id and today in the task's zone, else UTC's |
| `DELETE /api/tasks/{id}` | | 204 |

Every `/api` endpoint except login needs the session cookie (401 otherwise).
Writes from another site (an `Origin` header that isn't this site) get 403.

**For AI agents** (see [Talking to it from Claude](#talking-to-it-from-claude-mcp)), outside `/api`:

| Method and path | What it is |
|---|---|
| `POST /mcp` | The MCP endpoint (Streamable HTTP, stateless, JSON answers): the tools below. Needs `Authorization: Bearer <access token>`; without one it answers 401 with `WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource/mcp"`, which is how an agent finds the sign-in |
| `GET /.well-known/oauth-protected-resource` (also `…/mcp`) | Which server signs agents in (RFC 9728): this one |
| `GET /.well-known/oauth-authorization-server` | The OAuth endpoints (RFC 8414): PKCE S256 only, public clients only |
| `POST /oauth/register` | An agent registers itself (RFC 7591) and gets a `client_id`. Its `redirect_uris` must be Claude's, Gemini's or this machine's (`localhost`), else 400 |
| `GET /oauth/authorize` | The sign-in page the agent sends you to: your username and password (or nothing, if this browser is logged in to Taskly), then **Allow** or **Cancel** |
| `POST /oauth/token` | Swaps the one-time code for an access token (1 hour) and a refresh token (90 days, replaced each time it's used); also takes a refresh token |

The site's address in these answers comes from the request (`https://<site>` behind Caddy,
`http://localhost:8000` locally), so there is nothing to configure.

A task is `{"id", "list_id", "title", "status", "done", "due_date", "due_time", "due_zone",
"notes", "repeat", "created_by", "done_by", "created_at", "updated_at"}`: `status` is `"new"`, `"progress"` (in progress) or
`"done"`, and `done` is `status == "done"` (kept for pages and agents from before
statuses); `due_date` is a calendar day (`"2026-10-17"`, no time or zone; anything
else answers 422) or `null`, and the page decides by the device's own date whether
it is today, tomorrow or overdue; a task with a time (an appointment) also has
`due_time`, a 24-hour clock time (`"15:00"`), in `due_zone`, the IANA time zone of
whoever set it (`"America/New_York"`), so it is one moment for everyone and each
device shows it in its own time (3 pm in Florida is 8 pm in the Canaries), else both
`null`; `notes` is plain text (links, details; line breaks kept, and the page
shows web addresses as links) or `null`, never `""`; `repeat` is how it repeats from
its due date, or `null`: a small part of iCalendar's RRULE (`FREQ=DAILY|WEEKLY|MONTHLY|YEARLY`,
`INTERVAL`, `BYDAY=MO,TH` for weeks, `BYMONTHDAY` and `BYMONTH`), plus `FROM=DONE`
to count from the day it's finished instead of the schedule, stored with the parts
left out taken from the due date (`taskly/repeats.py` has the rules). On the
schedule the next one is due on its first day after the due date that isn't before
today (missed ones are skipped); people by username (`null` for tasks from before
accounts), times in UTC set by the server (`2026-09-28T12:00:00Z`). Task ids are
UUIDs the page makes itself. Titles are trimmed and 1–500 characters, notes up to
2000, repeat rules up to 200, list names 1–100 (422 otherwise). Anything in a list you're not in answers 404, as if it
didn't exist; an owner's action by a member answers 403. Interactive docs are at
`/docs` when `API_DOCS=true` is in `.env` (off by default, and on the VM: the
site is public).

## Accounts

There is no sign-up page: the admin creates every account. Hand passwords over
in person, not through chat.

On the VM, in `~/taskly` (`docker compose exec app python -m taskly.admin …`), or
locally (`.venv\Scripts\python.exe -m taskly.admin …`):

| To | Run |
|---|---|
| Create an account | `add-user maria`, then type the password twice, or press Enter to get a random one printed |
| Set a new password (also logs them out everywhere and disconnects their agents) | `reset-password maria` |
| Block someone (logs them out, disconnects their agents; their name stays on what they did) | `disable-user maria` |
| Let them back in | `enable-user maria` |
| Log someone out everywhere and disconnect their agents (a lost phone) | `revoke-sessions maria` |
| See everyone, with their sessions and connected agents | `list-users` |

A list without an owner (the old list "Taskly", if it was migrated before any account existed) goes to the next account created. Disabling someone hands each list they own to the active member who joined it earliest; with no other active member, the list keeps its (disabled) owner.

For example, to create an account on the VM:

```bash
cd ~/taskly
docker compose exec app python -m taskly.admin add-user <name>
```

It asks for the password twice (at least 6 characters). Press Enter at the
first prompt instead to have one made up and printed. Do this once per person.
Names are 2–32 letters, digits, `.`, `_` or `-`; capitals don't matter when
logging in, and the page shows the name as it was created.

People can change their own password on the page; that also logs out their
other devices and disconnects their agents. Logins last 90 days from the last time the device was used.
After 10 wrong passwords for a name (or 30 from one address) in 15 minutes,
logins wait up to 15 minutes.

**Locally:** create yourself an account once with
`.venv\Scripts\python.exe -m taskly.admin add-user me`, then log in on the page.

## On your phone

Open `https://<site>/`, log in, then install it. **Download** in the menu (☰, top right) does it
in Chrome and Edge, and shows these steps elsewhere (it's hidden in the installed app):

- **iPhone (Safari):** Share → **Add to Home Screen**. Do this: Safari deletes a
  website's saved data after 7 days without a visit, but not an installed app's,
  and unsent changes live there.
- **Android (Chrome):** menu → **Install app** (or "Add to Home screen").
- **Laptop (Chrome or Edge):** the install icon at the end of the address bar.

**Offline** you can see and search your lists, add, tick, rename and delete tasks, set their due dates, repeats and notes, and clear a list's done ones; finishing a repeating task shows the next one at once. The
line at the bottom says how many changes are waiting; they're sent when you're
back online and the app is open (it doesn't sync in the background). It syncs
when opened, every 30 seconds while open, and when you press **Sync** in the menu. Creating
lists, settings and logging out need a connection. If someone deleted a task you
changed offline, your change is dropped and the app says so.

**Light or dark:** it follows the device until you tap the sun/moon button at the
top; that choice stays on the device until you log out.

**Logging out** removes everything Taskly saved on the device. If changes
haven't synced yet, it asks first. Someone else logging in on the same device
never sees or sends your unsent changes.

**Checking a new version on a phone:** after a deploy, close and reopen the app
(it updates on open). Then: go offline (airplane mode), tick a task, add one,
reopen the app (still there, "2 changes waiting"), go online, and check another
device shows the changes.

## Talking to it from Claude (MCP)

Taskly is an MCP server: connect it to Claude once, then ask things like "what's
still open on Groceries?", "make a list Weekend with bread, eggs and coffee" or
"tick off the milk". Claude works as you, with the same rights as you have on the page,
and the page shows the changes on its next sync.

**What the agent can do** (the tools):

| Tool | Does |
|---|---|
| `list_lists` | Your lists: name, owner, members, and how many tasks are open (in progress included), in progress, and done |
| `list_tasks` | The open tasks of one list (by name or id) or of every list, soonest due first, then the rest oldest first, each with its `status`, `notes`, `due_date`, any `due_time` (in `due_zone`) and `repeat`; `include_done` adds the finished ones |
| `create_list` | Makes a list you own |
| `rename_list` | Renames a list you own |
| `delete_list` | Deletes a list you own, with its tasks, for everyone on it (no undo; Claude asks first) |
| `add_tasks` | Adds tasks (up to 50) to a list, by name or id: `titles` for plain ones, `tasks` for ones with `notes`, a `due_date` (and `due_time` with its `due_zone`) or a `repeat` (an RRULE like `FREQ=WEEKLY;BYDAY=MO`) |
| `complete_task` | Closes a task; `done: false` opens it again. Closing a repeating one answers with `next`, the task it made; `today` (your date) is the day the next one counts from |
| `set_task_status` | Moves a task to `new`, `progress` (in progress) or `done`, like the page's board; `done` on a repeating one answers with `next`, as `complete_task` does |
| `update_task` | Changes a task's `title`, `notes`, `due_date` (with `due_time` and `due_zone`) or `repeat`; what's left out (or `null`) stays, and `""` removes the notes, the due date or the repeat |
| `delete_task` | Deletes a task for everyone on its list (no undo; Claude asks first) |
| `clear_done` | Deletes a list's finished tasks for everyone on it, like the page's "Clear done" (no undo; Claude asks first) |

A time needs its time zone (`America/New_York`): Claude asks you for yours if it doesn't
know it. It can't change members; use the page for that.

**Connecting Claude (web, desktop and phone apps).** Your plan must allow custom connectors
(Pro and Max do). Add it on the web or in the desktop app; the phone app then has it too.

1. In Claude: **Customize** (or Settings) → **Connectors** → **Add custom connector**.
2. Name: `Taskly`. URL: `https://<site>/mcp`, exactly, without a slash at the end. Leave the
   OAuth client ID and secret empty (or choose "Register automatically" if it asks).
3. **Connect**. A Taskly page opens: sign in with your Taskly username and password
   (if that browser is already logged in to Taskly, it just shows your name), check it says
   **Claude (claude.ai)**, and press **Allow**.
4. In a chat, make sure Taskly is switched on in the tools menu, then ask.

Claude may ask you before it uses a tool that changes something; you can let it always allow one.

This worked on the first try on claude.ai (October 2026), with the OAuth fields left empty.

**If Chrome shows a red "Dangerous site" page** for the site (or for the sign-in tab while
connecting): that's Google Safe Browsing, not the server. Free dynamic-DNS names like ours
share a poor reputation, and a password form there gets flagged as phishing. To get past it
yourself: **Details → visit this unsafe site**. To get it lifted: in Google Search Console, add
the site as a URL-prefix property, verify it (a DNS TXT record; DuckDNS sets one with
`https://www.duckdns.org/update?domains=<name>&token=<token>&txt=<value>`), then **Security
issues → Request review**. A domain of our own is the lasting fix.

**Claude Code:**

```bash
claude mcp add --transport http taskly https://<site>/mcp
```

Then run `/mcp` in Claude Code, pick `taskly` and sign in in the browser it opens. To try
your local copy, use `http://localhost:8000/mcp` (uvicorn running, an account made with
`taskly.admin add-user`).

**Gemini.** The server follows the same standard (MCP with OAuth and dynamic
registration), and Gemini's sign-in addresses are allowed. As of October 2026 it hasn't
been tried: the Gemini app's "Custom apps" is US-only and its OAuth sign-in was
reported to fail on Google's side, and Gemini CLI no longer accepts Google AI Pro/Ultra
subscriptions. If you try it, add `https://<site>/mcp` the same way and note here what happened.

**Disconnecting.** Remove the connector in Claude. That doesn't tell Taskly, so to cut
off every agent you connected, change your password on the page, or on the VM run
`taskly.admin revoke-sessions <name>` (it logs you out everywhere too). Access tokens
last an hour; an agent left unused for 90 days has to sign in again.

**Behind it:** Taskly signs agents in itself (OAuth 2.1, in `oauth_routes.py`): no
outside service, and the same accounts, passwords and login throttle as the page. Codes and
tokens are stored hashed (`oauth_*` tables, see [The database](#the-database)). Caddy needs
no change: `reverse_proxy taskly:8000` already passes `/mcp`, `/oauth/` and `/.well-known/`.

## Layout

```
taskly/
  main.py       create_app(): runs the migrations, adds the routes, serves the built page
  settings.py   Settings (DB_PATH, STATIC_DIR, API_DOCS), read from the environment and .env
  db.py         the SQLite connection and the schema migrations
  routes.py     the HTTP endpoints
  oauth.py      AI agents' sign-in: the queries (clients, codes, grants, tokens) and the allowed redirect addresses
  oauth_routes.py   the OAuth endpoints and discovery documents (/oauth/*, /.well-known/*)
  oauth_page.py the sign-in and Allow page for agents (server-made HTML)
  mcp_server.py /mcp: the MCP tools, and the guard that checks the bearer token
  deps.py       the per-request database connection
  auth.py       the session cookie, the login check, the throttle, the cross-site guard
  passwords.py  password hashing (scrypt)
  users.py      the account queries
  sessions.py   the login session queries
  lists.py      lists and members: the queries
  tasks.py      tasks: the queries
  repeats.py    repeating tasks: the rules (a part of RRULE) and the next one's due date
  snapshot.py   what a user can see (GET /api/sync)
  admin.py      python -m taskly.admin: create and manage accounts
  backup.py     python -m taskly.backup: copy the database to data/backups/
  migrate.py    python -m taskly.migrate: apply pending migrations
  static/       the built page (not in git)
frontend/
  src/          the page: React + TypeScript (api.ts calls the API; sync.ts sends the queued task changes and downloads /api/sync)
    store.ts, view.ts, sync.ts, device.ts, useLocal.ts, StatusLine.tsx   the device's copy (IndexedDB) and its queue of unsent changes, what the screen shows, syncing, the page's one store and sync, the hook that triggers syncs, the "N changes waiting" line
    Login.tsx, Header.tsx, ChangePassword.tsx   the login screen, the header (screen tabs, your name, light/dark, the menu) and the phone's tab bar, the password form
    ListsPage.tsx   everything after logging in: the header and the Today, List, Board and Focus screens
    TodayScreen.tsx, today.ts   the Today screen: from every list, what's overdue, due today and in progress, then what was done today; its add bar adds a task due today to the list picked there
    ListScreen.tsx, TaskItem.tsx, NewList.tsx, ListSettings.tsx   the List screen: the picker, the "Due today" filter, the add bar, the tasks, new list, members and rename/delete
    DuePicker.tsx, due.ts   a task's due date and time: the picker under a task (Today, Tomorrow, any day, none; a time if you like; how it repeats), and the chips' labels (today, tomorrow, overdue) and the filter, by the device's date and time zone
    TaskNotes.tsx, notes.ts   a task's notes: the text with its web addresses as links, and the editor under a task
    repeat.ts, repeat.cases.json   repeating tasks: the picker's Repeat choices, what the chip says, and the next one's due date (the cases are the server's test cases too)
    BoardScreen.tsx   the Board: New, In progress and Done columns; buttons move a card, and on a desktop so does dragging it
    ClearDone.tsx   "Clear done" (List and Board): deletes a list's finished tasks after an inline confirmation
    SearchScreen.tsx, search.ts   search every list (the header's magnifier), on the device's copy
    FocusScreen.tsx, timer.ts, useTimer.ts   the Focus screen's pomodoro timer, the task focused on and the sessions per task (kept on the device only)
    stages.ts     a task's stage (status): labels, the Board's buttons and drops, the List's and Today's headlines
    Chrome.tsx, style.css, useWide.ts   shared pieces (wordmark, avatar, blobs), the "Organic" look (Archivo, bundled locally), desktop vs phone at 900px
    pickList.ts, screen.ts   which list and which screen are open
    messages.ts   the text shown for API errors
  public/       the icon (icon.svg) and the PNGs made from it (`npm --prefix frontend run icons`)
  vite.config.ts   Vite and the PWA plugin (manifest and service worker)
tests/
scripts/deploy.ps1
docs/
  data-model.html   the database drawn, interactive; data-model.svg is its picture (above)
  superpowers/      the design spec and the plan of each phase, as written at the time
```

## The database

One SQLite file: `/data/taskly.db` in the container, which is
`~/taskly/data/taskly.db` on the VM. Deploys back it up and apply new migrations to it, but never replace it.

![The tables in taskly.db at schema 9: users, sessions, lists, list_members and tasks, and for AI agents oauth_clients, oauth_codes, oauth_grants and oauth_tokens, and the columns that point from one to another](docs/data-model.svg)

[`docs/data-model.html`](docs/data-model.html) is the same diagram, interactive (open it
from a clone in a browser): select a table, column or line for its rules and the code that
uses it, step through schema versions 1 to 9, and see what `/api/sync` sends and what the
phone keeps in IndexedDB.

**Changing the schema:** append an SQL string to `MIGRATIONS` in `db.py`, for
example `"ALTER TABLE lists ADD COLUMN color TEXT;"`. On startup the app runs
every migration the file hasn't had yet (it tracks them in `PRAGMA
user_version`), each in its own transaction. Never edit or reorder a migration
that has been deployed: the VM's database already ran it and won't run it again.
Then add the change to `MODEL` in `docs/data-model.html`, open that page, press
**Copy the diagram as SVG** and save it over `docs/data-model.svg`.

**Backups.** Every deploy copies the database to
`~/taskly/data/backups/taskly-<UTC time>.db` before migrating, and keeps the
newest 10. A backup taken right before a migration is named
`taskly-<UTC time>-before-schema-<N>.db` and the rotation never deletes it;
delete those by hand when you're sure you won't go back. Being root's, they need
a throwaway container, like the restore below:

```bash
docker run --rm --network none -v ~/taskly/data:/data taskly-app sh -c 'rm /data/backups/taskly-<time>-before-schema-3.db'
```

To make one by hand (safe while the app runs):

```bash
cd ~/taskly
docker run --rm --network none -v ~/taskly/data:/data taskly-app python -m taskly.backup
```

**Restoring a backup.** The files in `data/` belong to root (the container's
user), so the copying happens in a throwaway container. With the app stopped:

```bash
cd ~/taskly
docker compose stop app
docker run --rm --network none -v ~/taskly/data:/data taskly-app sh -c '
  cp /data/taskly.db /data/taskly-before-restore.db &&
  cp /data/backups/taskly-<time>.db /data/taskly.db &&
  rm -f /data/taskly.db-wal /data/taskly.db-shm'    # stale journal files would corrupt the restored copy
```

Going back to before phase 2 means restoring the `taskly-<time>-before-schema-3.db` file; the ordinary
backups taken after it are already schema 3.

Then, depending on why:

- **Same code, the data went wrong:** `docker compose start app`.
- **Going back to older code** (for example from before a migration that removed
  something): don't start the app here; the running image would migrate the
  restored database forward again. From your PC, deploy the older code:
  `.\scripts\deploy.ps1 -Branch <commit>`. It backs up, finds nothing to migrate,
  and starts the older app.

## Deploy

### How the VM is laid out

The VM runs one Caddy and several apps, each a separate Docker Compose project
in its own folder:

- `~/proxy`: Caddy. It owns ports 80 and 443, gets HTTPS certificates, and
  sends each host name in `~/proxy/Caddyfile` to its app over the Docker
  network `web`.
- `~/reels`: the Reels app.
- `~/taskly`: this app. It joins `web` as `taskly`, listens on 8000 inside the
  container, and on the VM itself only on `127.0.0.1:8001`.

A deploy rebuilds and restarts only `~/taskly`. Caddy and Reels keep running.

### Setting up a developer's PC (once per person)

You need three things, handed over on a USB stick, never through git or chat:

1. **The SSH private key** (`reels_oci`). Put it in `C:\Users\<you>\.ssh\`.
   OpenSSH refuses a key that other users can read, so restrict it in PowerShell:

   ```powershell
   icacls $HOME\.ssh\reels_oci /inheritance:r /grant:r "$($env:USERNAME):R"
   ```

2. **Its passphrase.** The deploy asks for it twice. To type it once per
   Windows login, enable the agent in an **Administrator** PowerShell:

   ```powershell
   Get-Service ssh-agent | Set-Service -StartupType Automatic
   Start-Service ssh-agent
   ```

   Then, in a normal window: `ssh-add $HOME\.ssh\reels_oci`.

3. **`scripts\deploy.local.psd1`** with the VM's IP, the site's host name and
   the key's path. Copy `scripts\deploy.local.example.psd1` and fill it in. Git
   ignores it, so the VM's address never ends up in the repo.

Check it works: `ssh -i $HOME\.ssh\reels_oci ubuntu@<vm-ip> "docker ps"`.

### Deploying

```powershell
.\scripts\deploy.ps1
```

It ships the last **commit** on `main` (`git archive`, so uncommitted changes
stay behind) and replaces the code in `~/taskly` with it, so files deleted in git
go on the VM too; `data/` and `.env` stay. Then, on the VM: it builds the new
image while the old app keeps serving, backs up the database, runs the pending
migrations with the new image, and only then replaces the app, deletes the image
it replaced, and waits up to a minute for `https://<site>/health`. If the build
or a migration fails, it stops there and the old app keeps running on the
unchanged database. `-Branch` deploys another branch; `-Config` points at
another settings file. `-Branch` also takes a commit hash. Code from before these
deploy steps existed must be deployed with the `deploy.ps1` of that same commit (its
image has no `taskly.backup`).

Whoever deploys last wins: the VM gets exactly that person's commit. **Pull
before you deploy**, so you don't roll back the other person's changes.

### First deploy (once, on the VM)

1. **DNS.** Create the DuckDNS subdomain and point it at the VM's IP, the same
   one as Reels. Check it with `nslookup <site>`. No new firewall ports: all
   sites share 80 and 443.
2. **Deploy** with `.\scripts\deploy.ps1`. The health check at the end fails
   this first time because Caddy doesn't know the site yet. Check the app itself
   on the VM with `curl localhost:8001/health`.
3. **Add the site to Caddy.** Add this block to `~/proxy/Caddyfile` and apply it
   as in [Editing the Caddyfile](#editing-the-caddyfile):

   ```
   <site> {
       reverse_proxy taskly:8000
   }
   ```

   Caddy gets the certificate by itself within a minute.
4. **Create the accounts** as in [Accounts](#accounts) and open `https://<site>/`.

### On the VM

Run these inside `~/taskly`. Compose tells apps apart by folder, so the same
command in `~/reels` acts on Reels instead.

| To | Run |
|---|---|
| See the logs | `docker compose logs -f app` |
| Restart | `docker compose restart app` |
| Check the app without Caddy | `curl localhost:8001/health` |
| See Caddy's logs | `cd ~/proxy && docker compose logs -f caddy` |
| Change a setting | Edit `~/taskly/.env`, then `docker compose up -d` (a restart doesn't re-read it) |

### Moving from Caddy's password to accounts (once, when phase 1b ships)

1. Deploy. Caddy still asks for its password, so for a few minutes people log in twice.
2. Create everyone's account (see [Accounts](#accounts)).
3. In `~/proxy/Caddyfile`, remove the `@protected` line and the `basic_auth { … }`
   block from the site's block, leaving `reverse_proxy taskly:8000`. Validate and
   reload as in [Editing the Caddyfile](#editing-the-caddyfile).
4. In a private browser window, `https://<site>/` shows Taskly's own login and no
   browser password prompt.

## Caddy: the address

Caddy runs in `~/proxy` and is **shared with Reels**: one Caddyfile, one
container, every site. For Taskly it only does HTTPS and forwarding; the logins
are the app's own (see [Accounts](#accounts)). A mistake there can affect Reels too, so always
validate before reloading. A reload that fails changes nothing: Caddy keeps
running the config it had, and both sites stay up.

### Editing the Caddyfile

Every command runs in `~/proxy`. Caddy is not installed on the VM itself, only
inside the container, so each `caddy` command goes through Docker.

1. Edit with `nano Caddyfile`. Nano writes the file in place. Editors that
   write a new file instead leave the container seeing the old one; if an edit
   seems ignored, `docker compose exec caddy grep -n <site> /etc/caddy/Caddyfile`
   shows what Caddy sees, and `docker compose up -d --force-recreate caddy`
   picks up the new file (Reels drops for a second or two).
2. Check it, then apply it:

   ```bash
   docker compose exec -w /etc/caddy caddy caddy validate    # ends with "Valid configuration"
   docker compose exec -w /etc/caddy caddy caddy reload      # no downtime for either site
   docker compose logs --tail 30 caddy                       # certificates, errors
   ```

   The `-w /etc/caddy` matters: without it Caddy looks in the wrong folder and
   answers "no config file to load".
3. Optional: tidy the indentation. A reload warns "Caddyfile input is not
   formatted" when it's uneven, which is harmless. The container can only read
   the file, so format it with a throwaway container, then reload:

   ```bash
   docker run --rm -v ~/proxy/Caddyfile:/etc/caddy/Caddyfile caddy:2 caddy fmt --overwrite /etc/caddy/Caddyfile
   ```

### Changing the address

1. Create the new DuckDNS subdomain, pointing at the same IP, and check it
   with `nslookup <new site>`.
2. Replace the site name on the block's first line in the Caddyfile. Validate
   and reload. Caddy gets the new certificate by itself.
3. Change `Site` in every developer's `scripts\deploy.local.psd1`, or the
   deploy's health check waits on the old address.

### When something goes wrong

| What you see | Why | Fix |
|---|---|---|
| `Error: no config file to load` on reload | `-w /etc/caddy` is missing | Use the commands in [Editing the Caddyfile](#editing-the-caddyfile) |
| `WARN Caddyfile input is not formatted` | Uneven indentation | Harmless. Format it (step 3 above) if you like |
| `caddy: command not found` | Caddy exists only inside the container | Prefix with `docker compose exec -w /etc/caddy caddy` |
| Browser: `ERR_CONNECTION_CLOSED` | Caddy has no block for that name: the reload didn't happen or failed, or the name is misspelled | Validate, reload, check the logs |
| An edit seems ignored | The editor replaced the file and the container still sees the old one | `docker compose up -d --force-recreate caddy` |
| Browser: 502 | Caddy is fine but can't reach the app | `curl localhost:8001/health` on the VM; `docker network inspect web` should list `taskly-app-1` |
| Certificate errors in the logs | DNS doesn't point at the VM yet | `nslookup <site>`; fix the IP in DuckDNS, Caddy retries by itself |
| The deploy's health check fails but `curl localhost:8001/health` works | Caddy's side: a missing or wrong block, or `Site` in `deploy.local.psd1` doesn't match it | Compare the two names |

