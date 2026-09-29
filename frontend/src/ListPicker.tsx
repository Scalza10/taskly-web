// The row at the top: which list, its settings, and a new one.
import type { TaskList } from "./api";

type Props = {
  lists: TaskList[];
  current: TaskList | undefined;
  onChoose: (id: string) => void;
  onNew: () => void;
  onSettings: () => void;
};

export function ListPicker({ lists, current, onChoose, onNew, onSettings }: Props) {
  return (
    <div className="picker">
      {current ? (
        <select aria-label="list" value={current.id} onChange={(e) => onChoose(e.target.value)}>
          {lists.map((list) => <option key={list.id} value={list.id}>{list.name}</option>)}
        </select>
      ) : (
        <h1>Taskly</h1>
      )}
      {current && <button type="button" className="plain" onClick={onSettings}>Settings</button>}
      <button type="button" className="plain" onClick={onNew}>New list</button>
    </div>
  );
}
