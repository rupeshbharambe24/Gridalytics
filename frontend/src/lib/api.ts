const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetcher<T>(path: string, init?: RequestInit): Promise<T> {
  const token = typeof window !== "undefined" ? localStorage.getItem("gridalytics_token") : null;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const error = new Error(err.detail || res.statusText);
    (error as any).status = res.status;
    throw error;
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
  champion: Record<string, any>; models_available: string[]; all_models: any[];
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

export const getForecastRange = (resolution: string, start: string, end: string, model?: string) =>
  fetcher<{
    timestamps: string[]; predicted_mw: number[]; lower_bound_mw: number[]; upper_bound_mw: number[];
    model_name: string; resolution: string; metadata: Record<string, any>;
  }>(`/api/v1/forecast/${resolution}/range?start=${start}&end=${end}${model ? `&model_name=${model}` : ""}`);

export const getForecastPeak = (resolution: string, date: string) =>
  fetcher<{ date: string; peak_mw: number; peak_time: string; avg_mw: number; min_mw: number }>(
    `/api/v1/forecast/${resolution}/peak?date=${date}`
  );

export const getAvailableModels = () =>
  fetcher<Record<string, string>>("/api/v1/forecast/models/available");

export const getSeasonalStats = () =>
  fetcher<{ seasons: { season: string; min_mw: number; max_mw: number; avg_mw: number; std_mw: number; days: number }[] }>(
    "/api/v1/dashboard/stats/seasonal"
  );

export const getPredictionHistory = (days: number) =>
  fetcher<{ entries: any[]; summary: any }>(`/api/v1/dashboard/prediction-history?days=${days}`);

export const getAccuracyTrend = (days: number) =>
  fetcher<{ dates: string[]; daily_mape: number[]; rolling_7d_mape: number[]; rolling_30d_mape: number[]; drift_status: string; threshold: number }>(
    `/api/v1/dashboard/accuracy-trend?days=${days}`
  );

export const getForecastWithModel = (resolution: string, date: string, model: string) =>
  fetcher<{
    timestamps: string[]; predicted_mw: number[]; lower_bound_mw: number[]; upper_bound_mw: number[];
    model_name: string; resolution: string; metadata: Record<string, any>;
  }>(`/api/v1/forecast/${resolution}?date=${date}&model=${model}`);

export const getSubregionForecast = (resolution: string, date: string) =>
  fetcher<{ date: string; resolution: string; regions: Record<string, { predicted_mw: number[]; peak_mw: number | null; avg_mw: number | null }> }>(
    `/api/v1/forecast/${resolution}/subregion?date=${date}`
  );

export const getAnomalies = (days: number = 30) =>
  fetcher<any[]>(`/api/v1/dashboard/anomalies?days=${days}`);

// --- Auth ---
export const login = (email: string, password: string) =>
  fetcher<{ access_token: string; token_type: string }>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });

export const register = (email: string, password: string, full_name: string) =>
  fetcher<{ access_token: string; token_type: string }>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, full_name }),
  });

export const getMe = () => {
  const token = typeof window !== "undefined" ? localStorage.getItem("gridalytics_token") : null;
  if (!token) return Promise.reject(new Error("Not authenticated"));
  return fetcher<{ id: number; email: string; full_name: string; role: string }>("/api/v1/auth/me");
};

// --- Admin ---
export const getAdminModels = () => fetcher<any[]>("/api/v1/admin/models");

export const triggerRetrain = (resolution: string) =>
  fetcher<{ status: string }>("/api/v1/admin/retrain", {
    method: "POST",
    body: JSON.stringify({ resolution }),
  });

export const getRetrainStatus = () =>
  fetcher<{ status: string; resolution: string | null }>("/api/v1/admin/retrain/status");

export const getScraperStatus = () => fetcher<any>("/api/v1/admin/scraper-status");

export const getSchedulerJobs = () => fetcher<any[]>("/api/v1/admin/scheduler-jobs");
