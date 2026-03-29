const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// --- Health ---
export const getHealth = () => fetcher<{
  status: string; models_loaded: number; database: string;
  demand_latest: string | null; weather_latest: string | null;
}>("/api/v1/health/ready");

// --- Dashboard ---
export const getLive = () => fetcher<{
  current_demand_mw: number | null; timestamp: string | null;
  forecast_1h_mw: number | null; forecast_1h_lower: number | null; forecast_1h_upper: number | null;
  weather: Record<string, number>; today_peak_mw: number | null; today_peak_time: string | null;
  vs_yesterday_pct: number | null;
}>("/api/v1/dashboard/live");

export const getHistorical = (days: number, resolution = "hourly") =>
  fetcher<{
    timestamps: string[]; demand_mw: (number | null)[]; temperature: (number | null)[]; humidity: (number | null)[];
  }>(`/api/v1/dashboard/historical?days=${days}&resolution=${resolution}`);

export const getStats = () => fetcher<{
  today: Record<string, number | null>; yesterday: Record<string, number | null>;
  this_week_avg: number | null; last_week_avg: number | null; season: string; demand_trend: string;
}>("/api/v1/dashboard/stats/summary");

export const getHeatmap = (days = 30) => fetcher<{
  hours: number[]; days: string[]; values: number[][];
}>(`/api/v1/dashboard/heatmap?days=${days}`);

export const getModelPerformance = () => fetcher<{
  champion: Record<string, any>; models_available: string[];
}>("/api/v1/dashboard/model-performance");

// --- Forecast ---
export const getForecast = (resolution: string, date: string) =>
  fetcher<{
    timestamps: string[]; predicted_mw: number[]; lower_bound_mw: number[]; upper_bound_mw: number[];
    model_name: string; resolution: string; metadata: Record<string, any>;
  }>(`/api/v1/forecast/${resolution}?date=${date}`);

export const getWhatIf = (body: { date: string; resolution: string; overrides: Record<string, any> }) =>
  fetcher<{
    timestamps: string[]; predicted_mw: number[]; lower_bound_mw: number[]; upper_bound_mw: number[];
    model_name: string; metadata: Record<string, any>;
  }>("/api/v1/forecast/what-if", { method: "POST", body: JSON.stringify(body) });

export const getAvailableModels = () =>
  fetcher<Record<string, string>>("/api/v1/forecast/models/available");
