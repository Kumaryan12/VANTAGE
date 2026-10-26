export type Portfolio = {
  mode: "demo" | "kite";
  synthetic: boolean;
  currency: string;
  source: string;
  as_of: string;
  retrieved_at: string;
  price_timestamp_note: string;
  total_value: number;
  total_cost: number;
  unrealized_pnl: number;
  largest_weight: number;
  hhi: number;
  sectors: Record<string, number>;
  warnings: string[];
  holdings: {
    instrument: string;
    name: string;
    sector: string;
    quantity: number;
    last_price: number;
    average_price: number;
    value: number;
    weight: number;
    unrealized_pnl: number;
  }[];
};
export type Provenance = {
  source: string;
  synthetic: boolean;
  adjustment: string;
  currency: string;
  retrieved_at: string;
  start: string;
  end: string;
  content_hash: string;
};
export type Risk = {
  run_id: string;
  methodology: string;
  mode: string;
  confidence: number;
  horizon: string;
  loss_convention: string;
  weighting: string;
  sample_size: number;
  requested_window: number;
  start: string;
  end: string;
  annualized_volatility: number;
  historical_var: number;
  historical_var_amount: number;
  maximum_drawdown: number;
  tail_sample_mass: number;
  provenance: Provenance;
  series: {
    date: string;
    scenario_index: number;
    daily_return: number | null;
    drawdown: number;
    rolling_volatility: number | null;
  }[];
  instruments: string[];
  covariance: number[][];
  correlation: (number | null)[][];
  warnings: string[];
};
export type Source = {
  id: string;
  name: string;
  configured: boolean;
  purpose: string;
  note: string;
};
export type Dataset = { id: string; provenance: Provenance };
export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    cache: "no-store",
    credentials: "same-origin",
  });
  const body = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      body?.error?.code || "API_UNAVAILABLE",
      body?.error?.message ||
        "The backend could not be reached. Check that it is running.",
      body?.request_id,
    );
  return body as T;
}
export const money = (v: number, compact = false) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: compact ? 0 : 2,
    ...(compact ? { notation: "compact" as const } : {}),
  }).format(v);
export const pct = (v: number, digits = 2) => `${(v * 100).toFixed(digits)}%`;
export const dateLabel = (v: string) =>
  new Date(`${v}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
