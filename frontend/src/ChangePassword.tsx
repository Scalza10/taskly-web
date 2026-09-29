// Changing your password also logs out every other device (a lost phone, say).
import { useState, type FormEvent } from "react";
import { api } from "./api";
import { passwordMessage } from "./messages";

export function ChangePassword({ onDone }: { onDone: () => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [again, setAgain] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== again) return setError("The new passwords don't match.");
    try {
      await api("POST", "/api/me/password", { current, new: next });
      onDone();
    } catch (e) {
      setError(passwordMessage(e));
    }
  }

  return (
    <form className="stack panel" onSubmit={submit}>
      <label>
        Current password
        <input type="password" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />
      </label>
      <label>
        New password (at least 10 characters)
        <input type="password" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" minLength={10} required />
      </label>
      <label>
        New password again
        <input type="password" value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required />
      </label>
      <p className="hint">Your other devices will be logged out.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="row">
        <button type="submit">Change password</button>
        <button type="button" className="plain" onClick={onDone}>Cancel</button>
      </div>
    </form>
  );
}
