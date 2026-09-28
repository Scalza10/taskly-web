// The whole page: loads the list, and adds, ticks, renames and deletes todos through /api/todos.

const list = document.getElementById("todos");
const empty = document.getElementById("empty");
const errorBox = document.getElementById("error");
const form = document.getElementById("new-todo");
const titleInput = document.getElementById("new-title");

async function api(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) throw new Error(`${method} ${path} failed (${response.status})`);
  return response.status === 204 ? null : response.json();
}

function showError(error) {
  errorBox.textContent = error ? error.message : "";
  errorBox.hidden = !error;
}

function render(todos) {
  list.replaceChildren(...todos.map(renderTodo));
  empty.hidden = todos.length > 0;
}

function renderTodo(todo) {
  const item = document.createElement("li");
  item.classList.toggle("done", todo.done);

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = todo.done;
  checkbox.setAttribute("aria-label", "done");
  checkbox.addEventListener("change", () => change(() => api("PATCH", `/api/todos/${todo.id}`, { done: checkbox.checked })));

  // Click the title to rename; Enter or leaving the field saves, Escape cancels.
  const title = document.createElement("span");
  title.className = "title";
  title.textContent = todo.title;
  title.addEventListener("click", () => {
    title.contentEditable = "plaintext-only";
    title.focus();
  });
  title.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); title.blur(); }
    if (event.key === "Escape") { title.textContent = todo.title; title.blur(); }
  });
  title.addEventListener("blur", () => {
    title.contentEditable = "false";
    const newTitle = title.textContent.trim();
    if (!newTitle) { title.textContent = todo.title; return; }
    if (newTitle !== todo.title) change(() => api("PATCH", `/api/todos/${todo.id}`, { title: newTitle }));
  });

  const remove = document.createElement("button");
  remove.className = "delete";
  remove.textContent = "×";
  remove.setAttribute("aria-label", `delete "${todo.title}"`);
  remove.addEventListener("click", () => change(() => api("DELETE", `/api/todos/${todo.id}`)));

  item.append(checkbox, title, remove);
  return item;
}

// Runs one change, then reloads the list, so the page always shows what the server has.
async function change(request) {
  try {
    await request();
    showError(null);
  } catch (error) {
    showError(error);
  }
  await refresh();
}

async function refresh() {
  try {
    render(await api("GET", "/api/todos"));
  } catch (error) {
    showError(error);
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = titleInput.value.trim();
  if (!title) return;
  await change(() => api("POST", "/api/todos", { title }));
  titleInput.value = "";
  titleInput.focus();
});

refresh();
