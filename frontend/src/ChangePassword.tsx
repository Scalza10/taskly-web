// Changing your password also logs out every other device (a lost phone, say).
import { useState, type FormEvent } from "react";
import { api } from "./api";
import { passwordMessage } from "./messages";

export function ChangePassword({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (next !== again) return setError("The new passwords don't match.");
    setBusy(true);
    try {
      await api("POST", "/api/me/password", { current, new: next });
      onDone();
    } catch (e) {
      setError(passwordMessage(e));
      setBusy(false);
    }
  }

  return (
    <form className="stack panel" onSubmit={submit}>
      <label>
        Current password
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      </label>
      <label>
        New password (at least 6 characters)
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={6} required />
      </label>
      <label>
        New password again
        <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
      </label>
      <p className="hint">Your other devices will be logged out.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy}>Change password</button>
        <button type="button" className="plain" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}
