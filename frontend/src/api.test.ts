import { afterEach, expect, test, vi } from "vitest";
import { api, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

const LIST = "/api/lists/0b5e2c1a-3f4d-4e6a-9b7c-8d9e0f1a2b3c";

function answer(status: number, body?: unknown) {
  const fetch = vi.fn(async () => new Response(body === undefined ? null : JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

test("sends JSON and returns the parsed answer", async () => {
  const fetch = answer(201, { name: "Groceries" });
  expect(await api("POST", "/api/lists", { name: "Groceries" })).toEqual({ name: "Groceries" });
  expect(fetch).toHaveBeenCalledWith("/api/lists", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: '{"name":"Groceries"}',
  });
});

test("a request without a body sends no Content-Type", async () => {
  const fetch = answer(200, { username: "maria" });
  await api("GET", "/api/me");
  expect(fetch).toHaveBeenCalledWith("/api/me", { method: "GET", headers: {}, body: undefined });
});

test("204 resolves to null", async () => {
  answer(204);
  expect(await api("DELETE", LIST)).toBeNull();
});

test("an error uses the server's detail when it is text", async () => {
  answer(404, { detail: "No such list" });
  const error = (await api("PATCH", LIST, { name: "Shop" }).catch((e) => e)) as ApiError;
  expect(error).toBeInstanceOf(ApiError);
  expect(error.status).toBe(404);
  expect(error.message).toBe("No such list");
});

test("an error without a text detail says what failed", async () => {
  answer(422, { detail: [{ msg: "too long" }] });
  const error = (await api("POST", "/api/lists", { name: "x" }).catch((e) => e)) as ApiError;
  expect(error.message).toBe("POST /api/lists failed (422)");
});
