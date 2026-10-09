// "Offline · 3 changes waiting", "Synced 2 min ago", and notes about changes that couldn't apply.
import { useEffect, useState } from "react";
import { sync } from "./device";
import type { Local } from "./useLocal";
import { statusText } from "./view";

export function StatusLine({ local }: { local: Local }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const { connection, notes } = local.sync;
  return (
    <>
      <div className={`status ${connection}`} role="status">
        <span className="status-dot" aria-hidden="true" />
        {statusText(connection, local.queue.length, local.stored?.syncedAt, now)}
      </div>
      {notes.length > 0 && (
        <div className="notes error">
          {notes.length === 1 ? notes[0] : `${notes.length} changes couldn't be applied.`}{" "}
          <button type="button" className="text" onClick={() => sync.dismissNotes()}>OK</button>
        </div>
      )}
    </>
  );
}
