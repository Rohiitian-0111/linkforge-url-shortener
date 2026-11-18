import type { Session } from "./types";

const SESSION_KEY = "linkforge.session.v1";
const API_BASE = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    if (
      !parsed.access_token ||
      !parsed.user?.id ||
      typeof parsed.expires_at !== "number" ||
      parsed.expires_at <= Date.now()
    ) {
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function saveSession(session: Session | null) {
  try {
    if (session) sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
    else sessionStorage.removeItem(SESSION_KEY);
  } catch {
    // A browser can disallow storage; the in-memory session still works.
  }
}

export async function request<T>(
  path: string,
  token?: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    throw new ApiError(
      "Could not reach the server. Check your connection and try again.",
      0,
    );
  }
  if (!response.ok) {
    let message = `The request failed (${response.status}). Please try again.`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) {
        message = body.detail
          .map((item: { loc?: string[]; msg?: string }) => {
            const field = item.loc?.slice(1).join(" ").replaceAll("_", " ");
            return `${field ? `${field}: ` : ""}${item.msg || "Invalid value"}`;
          })
          .join(". ");
      }
    } catch {
      /* Retain the HTTP status fallback for non-JSON responses. */
    }
    if (response.status === 429) {
      const retry = response.headers.get("Retry-After");
      if (retry) {
        const punctuation = /[.!?]$/.test(message) ? "" : ".";
        message += `${punctuation} Try again in ${retry} seconds.`;
      }
    }
    if (response.status === 401 && token)
      window.dispatchEvent(new Event("linkforge:unauthorized"));
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const humanError = (error: unknown): string =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";
