import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

function answer(status: number, body?: unknown) {
  const fetch = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

test("sends JSON and returns the parsed answer", async () => {
  const fetch = answer(201, { id: 1 });
  expect(await api("POST", "/api/todos", { title: "x" })).toEqual({ id: 1 });
  expect(fetch).toHaveBeenCalledWith("/api/todos", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: '{"title":"x"}',
  });
});

test("a request without a body sends no Content-Type", async () => {
  const fetch = answer(200, []);
  await api("GET", "/api/todos");
  expect(fetch).toHaveBeenCalledWith("/api/todos", { method: "GET", headers: {}, body: undefined });
});

test("204 resolves to null", async () => {
  answer(204);
  expect(await api("DELETE", "/api/todos/1")).toBeNull();
});

test("an error uses the server's detail when it is text", async () => {
  answer(404, { detail: "No such todo" });
  const error = (await api("PATCH", "/api/todos/9", { done: true }).catch((e) => e)) as ApiError;
  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(404);
  expect(error.message).toBe("No such todo");
});

test("an error without a text detail says what failed", async () => {
  answer(422, { detail: [{ msg: "too long" }] });
  const error = (await api("POST", "/api/todos", { title: "x" }).catch((e) => e)) as ApiError;
  expect(error.message).toBe("POST /api/todos failed (422)");
});
