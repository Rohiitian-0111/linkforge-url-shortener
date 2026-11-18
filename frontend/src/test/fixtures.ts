import type { Analytics, Dashboard, Link, User } from "../types";

// Test data only. Production screens render responses from the real API.
export const TEST_USER: User = {
  id: "2e6eec6e-3914-4769-8e6d-0b24d45fb2e8",
  email: "asha@example.com",
  name: "Asha Rao",
  created_at: "2026-11-01T08:00:00Z",
};

export const TEST_LINK: Link = {
  id: "a70b4f02-4acf-49ed-9acc-5f9921c783f6",
  original_url: "https://example.com/project-notes",
  short_code: "notes",
  short_url: "http://localhost:8080/r/notes",
  title: "Project notes",
  is_active: true,
  created_at: "2026-11-16T08:00:00Z",
  expires_at: null,
  click_count: 5,
};

export const TEST_DASHBOARD: Dashboard = {
  total_links: 1,
  active_links: 1,
  total_clicks: 42,
  period_clicks: 5,
  clicks_by_day: [
    { date: "2026-11-16", clicks: 0 },
    { date: "2026-11-17", clicks: 2 },
    { date: "2026-11-18", clicks: 3 },
  ],
  top_links: [TEST_LINK],
};

export const TEST_ANALYTICS: Analytics = {
  url_id: TEST_LINK.id,
  short_code: TEST_LINK.short_code,
  total_clicks: 5,
  period_clicks: 5,
  days: 30,
  clicks_by_day: TEST_DASHBOARD.clicks_by_day,
  referrers: [
    { referrer: "example.com", clicks: 3 },
    { referrer: "Direct / unknown", clicks: 2 },
  ],
  devices: [
    { device: "mobile", clicks: 3 },
    { device: "desktop", clicks: 2 },
  ],
};
