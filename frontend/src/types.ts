export type Config = {
  name: string;
  source: "demo" | "custom";
  url: string;
  auth: string;
  pagination: string;
  items_path: string;
  cursor_path: string;
  more_path: string;
  page_size: number;
  max_pages: number;
  timeout: number;
  retries: number;
  incremental: boolean;
  mapping: Record<string, string>;
};
export type Row = {
  id: string;
  name: string;
  status: string;
  amount: number;
  updated_at: string;
};
export type Event = {
  id: number;
  time: string;
  level: string;
  code: string;
  message: string;
  hint?: string;
  page?: number;
};
export type Run = {
  id: string;
  status: string;
  started: string;
  ended?: string;
  scenario: string;
  pages: number;
  seen: number;
  inserted: number;
  updated: number;
  unchanged: number;
  retries: number;
  error?: string;
  since?: string;
  events?: Event[];
};
export type Notice = {
  message: string;
  hint?: string;
  code?: string;
  good?: boolean;
};
