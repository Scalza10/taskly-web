// Shown when there is no session. Accounts are made by the admin (python -m taskly.admin add-user).
import { useState, type FormEvent } from "react";
import { api, type Me } from "./api";
import { Wordmark } from "./Chrome";
import { loginMessage } from "./messages";

export function Login({ onLoggedIn }: { onLoggedIn: (username: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await api("POST", "/api/login", { username: username.trim(), password });
      onLoggedIn((await api<Me>("GET", "/api/me")).username);
    } catch (e) {
      setError(loginMessage(e));
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="welcome">
      <Wordmark />
      <h1 className="headline">Log in.</h1>
      <form className="card stack" onSubmit={submit}>
        <label>
          Username
          <input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" required autoFocus />
        </label>
        <label>
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button type="submit" className="primary" disabled={busy}>Log in</button>
      </form>
    </main>
  );
}
