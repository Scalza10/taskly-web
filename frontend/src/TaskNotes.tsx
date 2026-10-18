// A task's notes: the text with its web addresses as links (each opens in a new tab), and the
// editor, a row under a task on the List screen like the due date picker: Save (or Ctrl+Enter),
// Remove notes, Cancel (or Escape). The links in the text show under the field too, since a
// field's text can't be clicked.
import { Fragment, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { NOTES_MAX, noteParts } from "./notes";

export function NotesText({ text }: { text: string }) {
  return (
    <>
      {noteParts(text).map((part, i) =>
        part.href ? (
          <a key={i} href={part.href} target="_blank" rel="noopener noreferrer" draggable={false}>{part.text}</a>
        ) : (
          <Fragment key={i}>{part.text}</Fragment>
        ),
      )}
    </>
  );
}

type Props = { title: string; value: string | null; onSave: (notes: string | null) => void; onCancel: () => void };

export function NotesEditor({ title, value, onSave, onCancel }: Props) {
  const [text, setText] = useState(value ?? "");
  const field = useRef<HTMLTextAreaElement>(null);
  const links = noteParts(text).filter((part) => part.href);
  const save = () => onSave(text.trim() || null);

  // The cursor goes to the end, to add to what's there.
  useEffect(() => {
    const end = field.current?.value.length ?? 0;
    field.current?.setSelectionRange(end, end);
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    save();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "Escape") onCancel();
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      save();
    }
  }

  return (
    <form className="notes-editor" aria-label={`notes of "${title}"`} onSubmit={submit} onKeyDown={onKeyDown}>
      <textarea
        ref={field}
        aria-label="notes"
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={NOTES_MAX}
        rows={Math.min(12, Math.max(3, text.split("\n").length + 1))}
        placeholder="Links, details…"
        autoFocus
      />
      {links.length > 0 && (
        <p className="notes-links">
          {links.map((link, i) => <a key={i} href={link.href} target="_blank" rel="noopener noreferrer">{link.text}</a>)}
        </p>
      )}
      <div className="notes-actions">
        <button type="submit" className="primary">Save</button>
        {value && <button type="button" className="text" onClick={() => onSave(null)}>Remove notes</button>}
        <button type="button" className="text" onClick={onCancel}>Cancel</button>
      </div>
    </form>
  );
}
