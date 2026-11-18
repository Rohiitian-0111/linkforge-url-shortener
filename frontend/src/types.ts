export interface User {
  id: string;
  email: string;
  name: string;
  created_at: string;
}

export interface Session {
  access_token: string;
  user: User;
  expires_at: number;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Link {
  id: string;
  original_url: string;
  short_code: string;
  short_url: string;
  title: string | null;
  is_active: boolean;
  created_at: string;
  expires_at: string | null;
  click_count: number;
}

export interface LinkList {
  items: Link[];
  total: number;
  page: number;
  page_size: number;
}

export interface DailyClicks {
  date: string;
  clicks: number;
}

export interface Dashboard {
  total_links: number;
  active_links: number;
  total_clicks: number;
  period_clicks: number;
  clicks_by_day: DailyClicks[];
  top_links: Link[];
}

export interface Analytics {
  url_id: string;
  short_code: string;
  total_clicks: number;
  period_clicks: number;
  days: number;
  clicks_by_day: DailyClicks[];
  referrers: { referrer: string; clicks: number }[];
  devices: { device: string; clicks: number }[];
}

export interface LinkInput {
  original_url: string;
  title: string;
  custom_alias?: string;
  expires_at?: string | null;
}

export type LinkStatus = "all" | "active" | "inactive" | "expired";
