import type { Link } from "./types";

export const count = (n: number) => new Intl.NumberFormat().format(n);
export const shortDate = (date: string) =>
  new Date(date).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
export const fullDate = (date: string) =>
  new Date(date).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });

export function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function displayUrl(url: string): string {
  return url.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

export function linkStatus(link: Link): "active" | "inactive" | "expired" {
  if (link.expires_at && new Date(link.expires_at).getTime() <= Date.now())
    return "expired";
  return link.is_active ? "active" : "inactive";
}

export function localDateTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}
