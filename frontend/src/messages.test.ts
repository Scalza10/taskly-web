import { expect, test } from "vitest";
import { ApiError } from "./api";
import { isLoggedOut, loginMessage, passwordMessage } from "./messages";

test("login messages", () => {
  expect(loginMessage(new ApiError(401, "Wrong username or password"))).toBe("Wrong username or password.");
  expect(loginMessage(new ApiError(429, "Too many"))).toBe("Too many attempts. Try again in a few minutes.");
  expect(loginMessage(new TypeError("Failed to fetch"))).toBe("Can't reach Taskly. Check your connection.");
  expect(loginMessage(new ApiError(500, "POST /api/login failed (500)"))).toBe("POST /api/login failed (500)");
});

test("password messages", () => {
  expect(passwordMessage(new ApiError(403, "The current password is wrong"))).toBe("The current password is wrong.");
  expect(passwordMessage(new ApiError(422, "Passwords need at least 10 characters"))).toBe("Passwords need at least 10 characters.");
  expect(passwordMessage(new ApiError(429, "x"))).toBe("Too many attempts. Try again in a few minutes.");
});

test("only a 401 means logged out", () => {
  expect(isLoggedOut(new ApiError(401, "Log in first"))).toBe(true);
  expect(isLoggedOut(new ApiError(403, "x"))).toBe(false);
  expect(isLoggedOut(new TypeError("Failed to fetch"))).toBe(false);
});
