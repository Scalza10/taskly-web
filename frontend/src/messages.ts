// What to tell people when a login or password change fails.
import { ApiError } from "./api";

const TOO_MANY = "Too many attempts. Try again in a few minutes.";
const OFFLINE = "Can't reach Taskly. Check your connection.";

export function isLoggedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export function loginMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return OFFLINE;
  if (error.status === 401) return "Wrong username or password.";
  if (error.status === 429) return TOO_MANY;
  return error.message;
}

export function passwordMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return OFFLINE;
  if (error.status === 429) return TOO_MANY;
  if (error.status === 403 || error.status === 422) return `${error.message}.`;
  return error.message;
}
