// Backend base: localhost during laptop dev; when the page is opened through a
// public tunnel (e.g. from a phone — HTTPS is required for mic), it targets the
// backend's tunnel from NEXT_PUBLIC_BACKEND_TUNNEL (set in frontend/.env.local).
const BACKEND_TUNNEL = process.env.NEXT_PUBLIC_BACKEND_TUNNEL || "http://localhost:8000";
export const API =
  typeof window !== "undefined" && !["localhost", "127.0.0.1"].includes(window.location.hostname)
    ? BACKEND_TUNNEL
    : "http://localhost:8000";

export async function post<T = unknown>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return r.json();
}

export async function get<T = unknown>(path: string): Promise<T> {
  const r = await fetch(`${API}${path}`);
  return r.json();
}

export function rupees(paise: number): string {
  return "₹" + (paise / 100).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export type WsEvent = { type: string; data: Record<string, unknown> };

export function connectWs(onEvent: (e: WsEvent) => void): () => void {
  let ws: WebSocket | null = null;
  let alive = true;
  let ping: ReturnType<typeof setInterval> | null = null;

  const open = () => {
    if (!alive) return;
    ws = new WebSocket(`${API.replace("http", "ws")}/ws`);
    ws.onmessage = (m) => {
      try { onEvent(JSON.parse(m.data)); } catch { /* ignore */ }
    };
    ws.onopen = () => {
      ping = setInterval(() => ws?.readyState === 1 && ws.send("ping"), 20000);
    };
    ws.onclose = () => {
      if (ping) clearInterval(ping);
      if (alive) setTimeout(open, 1500);
    };
  };
  open();
  return () => { alive = false; if (ping) clearInterval(ping); ws?.close(); };
}

export interface Failure {
  id: string; created_at: number; order_id: string; customer_name: string;
  customer_phone: string; amount: number; method: string; error_code: string;
  error_source: string; bank: string; kind: string; status: string;
  discount_pct?: number; payable_paise?: number;
}

export interface AuditRow {
  id: string; created_at: number; failure_id: string | null; category: string;
  rule: string | null; outcome: string; message: string; detail: string;
}

export interface QuietHours {
  start_h: number; end_h: number; hour_ist: number; in_quiet: boolean;
  default_start_h: number; default_end_h: number;
}

export interface Metrics {
  recovered_paise: number; recovered_count: number; mrr_saved_paise: number;
  mrr_saved_count: number; failures_count: number; at_risk_paise: number; yield_pct: number;
}
