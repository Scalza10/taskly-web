// Small pieces every screen shares: the wordmark, an avatar, the decorative blobs behind the
// page, the play and pause shapes (filled, unlike Lucide's), and the empty-state box.
import type { ReactNode } from "react";

export function Wordmark() {
  return (
    <div className="wordmark">
      <span className="pebble pebble-a" aria-hidden="true" />
      taskly
    </div>
  );
}

// The first letter of a username, as it's written ("s" for scalza).
export function Avatar({ name, size = "md" }: { name: string; size?: "sm" | "md" }) {
  return (
    <span className={`avatar avatar-${size}`} aria-hidden="true">
      {Array.from(name)[0] ?? "?"}
    </span>
  );
}

export function Blobs() {
  return (
    <div className="blobs" aria-hidden="true">
      <span className="blob blob-big pebble-a" />
      <span className="blob blob-small pebble-b" />
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty-box">{children}</p>;
}

export function PlayIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M7 4.5v15a1 1 0 0 0 1.5.86l12-7.5a1 1 0 0 0 0-1.72l-12-7.5A1 1 0 0 0 7 4.5z" />
    </svg>
  );
}

export function PauseIcon({ size }: { size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <rect x="6" y="4" width="4" height="16" rx="1.5" />
      <rect x="14" y="4" width="4" height="16" rx="1.5" />
    </svg>
  );
}
