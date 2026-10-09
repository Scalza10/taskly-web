"""The page an agent (Claude, Gemini) sends you to when you connect it: sign in if needed, then
Allow or Cancel. Plain HTML from the server, no script: it works in any in-app browser, and the
page's service worker never serves it (vite.config.ts leaves /oauth/ alone)."""

from html import escape
from urllib.parse import urlsplit

# No form-action: Chrome applies it to the redirect after the form, which goes to the agent's site.
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

STYLE = """
:root { color-scheme: light dark; --bg: #f6f6f4; --card: #fff; --text: #1d1d1b; --muted: #76766f;
        --line: #e2e2dc; --accent: #3b6fd8; --danger: #c43d3d; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #151514; --card: #1f1f1d; --text: #ecece6; --muted: #9a9a92; --line: #33332f;
          --accent: #7ea2f0; --danger: #e27272; }
}
body { margin: 0; background: var(--bg); color: var(--text); font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 420px; margin: 0 auto; padding: 32px 16px; }
h1 { margin: 0 0 16px; font-size: 26px; }
p { margin: 0 0 16px; }
.muted { color: var(--muted); }
.error { color: var(--danger); }
label { display: block; margin: 0 0 12px; }
input { box-sizing: border-box; width: 100%; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px;
        background: var(--card); color: inherit; font: inherit; }
.buttons { display: flex; gap: 12px; margin-top: 20px; }
button { flex: 1; padding: 10px 16px; border: 1px solid var(--line); border-radius: 8px; background: var(--card);
         color: inherit; font: inherit; cursor: pointer; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
a { color: var(--accent); }
"""


def _document(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(title)}</title><style>{STYLE}</style></head>"
        f"<body><main>{body}</main></body></html>"
    )


def agent_label(client_name: str, redirect_uri: str) -> str:
    """Who is asking, as HTML: the name the client registered, and the site the code will go to."""
    host = urlsplit(redirect_uri).hostname or ""
    where = "a program on this computer" if host in ("localhost", "127.0.0.1") else host
    name = client_name.strip() or "An app"
    return f"<strong>{escape(name)}</strong> <span class=\"muted\">({escape(where)})</span>"


def consent(*, client_name: str, redirect_uri: str, fields: dict[str, str], username: str | None,
            other_account_url: str, error: str = "") -> str:
    """username: who is signed in in this browser; None shows the username and password fields."""
    hidden = "".join(
        f'<input type="hidden" name="{escape(name)}" value="{escape(value)}">' for name, value in fields.items()
    )
    if username is None:
        account = (
            '<label>Username <input name="username" autocomplete="username" autocapitalize="none" required></label>'
            '<label>Password <input name="password" type="password" autocomplete="current-password" required></label>'
        )
    else:
        account = (
            f"<p>Signed in as <strong>{escape(username)}</strong>. "
            f'<a href="{escape(other_account_url)}">Use another account</a></p>'
        )
    message = f'<p class="error" role="alert">{escape(error)}</p>' if error else ""
    body = (
        "<h1>Connect to Taskly</h1>"
        f"<p>{agent_label(client_name, redirect_uri)} wants to see and change your Taskly lists and tasks.</p>"
        f'{message}<form method="post" action="/oauth/authorize">{hidden}{account}'
        '<div class="buttons"><button name="action" value="cancel" formnovalidate>Cancel</button>'
        '<button class="primary" name="action" value="allow">Allow</button></div></form>'
    )
    return _document("Connect to Taskly", body)


def problem(message: str) -> str:
    """A request we can't send back to the agent (unknown client or redirect): say so here."""
    return _document("Can't connect", f'<h1>Can\'t connect</h1><p class="error">{escape(message)}</p>'
                     '<p class="muted">Remove the connector in your AI app and add it again.</p>')
