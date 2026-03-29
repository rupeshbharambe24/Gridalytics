"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  TrendingUp, Calendar, Loader2, ArrowUpRight, ArrowDownRight, Download,
  Clock, Zap, BarChart3, ChevronDown,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { DemandChart } from "@/components/charts/demand-chart";
import { getForecast, getForecastRange, getForecastPeak } from "@/lib/api";

type Mode = "single" | "range";
type Resolution = "daily" | "hourly";
type RangePreset = "7d" | "14d" | "30d" | "90d" | "custom";

const RANGE_PRESETS: { label: string; value: RangePreset; days: number }[] = [
  { label: "7 Days", value: "7d", days: 7 },
  { label: "14 Days", value: "14d", days: 14 },
  { label: "30 Days", value: "30d", days: 30 },
  { label: "90 Days", value: "90d", days: 90 },
  { label: "Custom", value: "custom", days: 0 },
];

function addDays(dateStr: string, days: number) {
  const d = new Date(dateStr);
  d.setDate(d.getDate() + days);
  return d.toISOString().split("T")[0];
}

function exportCSV(result: any) {
  if (!result) return;
  const rows = [["Timestamp", "Predicted (MW)", "Lower Bound", "Upper Bound"]];
  result.timestamps.forEach((t: string, i: number) => {
    rows.push([t, result.predicted_mw[i].toFixed(1), result.lower_bound_mw[i].toFixed(1), result.upper_bound_mw[i].toFixed(1)]);
  });
  const csv = rows.map((r) => r.join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `edfs_forecast_${result.resolution}_${result.metadata?.date || "range"}.csv`;
  a.click();
}

export default function ForecastPage() {
  const [mode, setMode] = useState<Mode>("single");
  const [resolution, setResolution] = useState<Resolution>("hourly");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [rangePreset, setRangePreset] = useState<RangePreset>("7d");
  const [startDate, setStartDate] = useState(new Date().toISOString().split("T")[0]);
  const [endDate, setEndDate] = useState(addDays(new Date().toISOString().split("T")[0], 7));
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [peakData, setPeakData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    setPeakData(null);

    try {
      if (mode === "single") {
        const [forecast, peak] = await Promise.all([
          getForecast(resolution, date),
          getForecastPeak(resolution, date).catch(() => null),
        ]);
        setResult(forecast);
        setPeakData(peak);
      } else {
        const start = startDate;
        const end = rangePreset === "custom" ? endDate : addDays(startDate, RANGE_PRESETS.find((p) => p.value === rangePreset)!.days);
        const forecast = await getForecastRange(resolution, start, end);
        setResult(forecast);

        // Get peak for first day
        const peak = await getForecastPeak(resolution, start).catch(() => null);
        setPeakData(peak);
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const chartData = result
    ? result.timestamps.map((t: string, i: number) => ({
        time:
          resolution === "hourly"
            ? result.timestamps.length > 48
              ? new Date(t).toLocaleDateString("en-IN", { month: "short", day: "numeric", hour: "2-digit" })
              : new Date(t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
            : new Date(t).toLocaleDateString("en-IN", { month: "short", day: "numeric" }),
        demand: null as number | null,
      }))
    : [];

  const forecastData = result
    ? result.timestamps.map((t: string, i: number) => ({
        time: chartData[i]?.time,
        predicted: result.predicted_mw[i],
        lower: result.lower_bound_mw[i],
        upper: result.upper_bound_mw[i],
      }))
    : [];

  const peak = result ? Math.max(...result.predicted_mw) : null;
  const trough = result ? Math.min(...result.predicted_mw) : null;
  const avg = result ? result.predicted_mw.reduce((a: number, b: number) => a + b, 0) / result.predicted_mw.length : null;
  const totalMWh = result ? result.predicted_mw.reduce((a: number, b: number) => a + b, 0) : null;
  const peakIdx = result ? result.predicted_mw.indexOf(Math.max(...result.predicted_mw)) : -1;
  const peakTime = result && peakIdx >= 0 ? result.timestamps[peakIdx] : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Forecast</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          Predict electricity demand for any date — past or up to 90 days ahead
        </p>
      </motion.div>

      {/* Controls */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="rounded-xl border border-border bg-card p-5 space-y-4"
      >
        {/* Top Row: Mode + Resolution */}
        <div className="flex flex-wrap items-end gap-4">
          {/* Mode Toggle */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Mode</label>
            <div className="flex rounded-lg border border-border overflow-hidden">
              {(["single", "range"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`px-4 py-2 text-sm font-medium transition-colors ${
                    mode === m ? "bg-blue-600 text-white" : "bg-card text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m === "single" ? "Single Day" : "Date Range"}
                </button>
              ))}
            </div>
          </div>

          {/* Resolution */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Resolution</label>
            <div className="flex rounded-lg border border-border overflow-hidden">
              {(["hourly", "daily"] as const).map((r) => (
                <button
                  key={r}
                  onClick={() => setResolution(r)}
                  className={`px-4 py-2 text-sm font-medium transition-colors ${
                    resolution === r ? "bg-blue-600 text-white" : "bg-card text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Date Controls */}
          {mode === "single" ? (
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Date</label>
              <div className="relative">
                <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="pl-10 w-48 bg-background" />
              </div>
            </div>
          ) : (
            <>
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Range</label>
                <div className="flex rounded-lg border border-border overflow-hidden">
                  {RANGE_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => {
                        setRangePreset(p.value);
                        if (p.days > 0) setEndDate(addDays(startDate, p.days));
                      }}
                      className={`px-3 py-2 text-xs font-medium transition-colors ${
                        rangePreset === p.value ? "bg-blue-600 text-white" : "bg-card text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-muted-foreground">Start</label>
                <Input
                  type="date"
                  value={startDate}
                  onChange={(e) => {
                    setStartDate(e.target.value);
                    const preset = RANGE_PRESETS.find((p) => p.value === rangePreset);
                    if (preset && preset.days > 0) setEndDate(addDays(e.target.value, preset.days));
                  }}
                  className="w-44 bg-background"
                />
              </div>

              {rangePreset === "custom" && (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-muted-foreground">End</label>
                  <Input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="w-44 bg-background" />
                </div>
              )}
            </>
          )}

          {/* Predict */}
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            onClick={handlePredict}
            disabled={loading}
            className="flex items-center gap-2 px-6 py-2 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-500 disabled:opacity-50 transition-colors h-10"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
            {loading ? "Predicting..." : "Predict"}
          </motion.button>
        </div>
      </motion.div>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-400"
          >
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Results */}
      <AnimatePresence>
        {result && (
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="space-y-6">
            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0 }}
                className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Peak Demand</p>
                <div className="flex items-center gap-1.5 mt-1">
                  <ArrowUpRight className="w-4 h-4 text-amber-400" />
                  <span className="text-2xl font-bold font-mono text-amber-400">{peak?.toFixed(0)}</span>
                  <span className="text-xs text-muted-foreground">MW</span>
                </div>
                {peakTime && (
                  <p className="text-[10px] text-muted-foreground mt-1 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(peakTime).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}
                  </p>
                )}
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}
                className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Minimum</p>
                <div className="flex items-center gap-1.5 mt-1">
                  <ArrowDownRight className="w-4 h-4 text-blue-400" />
                  <span className="text-2xl font-bold font-mono text-blue-400">{trough?.toFixed(0)}</span>
                  <span className="text-xs text-muted-foreground">MW</span>
                </div>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
                className="rounded-xl border border-border bg-card p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Average</p>
                <span className="text-2xl font-bold font-mono mt-1 block">{avg?.toFixed(0)}</span>
                <span className="text-xs text-muted-foreground">MW</span>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                className="rounded-xl border border-border bg-card p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Total Energy</p>
                <span className="text-2xl font-bold font-mono mt-1 block">
                  {totalMWh ? (totalMWh / 1000).toFixed(1) : "---"}
                </span>
                <span className="text-xs text-muted-foreground">GWh</span>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
                className="rounded-xl border border-border bg-card p-4">
                <p className="text-[10px] text-muted-foreground uppercase tracking-wider">Model</p>
                <div className="flex items-center gap-2 mt-2">
                  <Badge variant="outline" className="text-xs bg-blue-500/10 text-blue-400 border-blue-500/20">
                    {result.model_name}
                  </Badge>
                </div>
                <p className="text-[10px] text-muted-foreground mt-1">
                  {result.predicted_mw.length} data points
                  {result.metadata?.mode && ` | ${result.metadata.mode}`}
                </p>
              </motion.div>
            </div>

            {/* Chart */}
            <DemandChart
              data={chartData}
              forecast={forecastData}
              title={
                mode === "single"
                  ? `${resolution === "hourly" ? "Hourly" : "Daily"} Forecast - ${date}`
                  : `${resolution === "hourly" ? "Hourly" : "Daily"} Forecast - ${result.metadata?.start || startDate} to ${result.metadata?.end || endDate}`
              }
              height={420}
            />

            {/* Data Table with Export */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="flex items-center justify-between p-4 border-b border-border">
                <h3 className="text-sm font-semibold">Prediction Data ({result.predicted_mw.length} points)</h3>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  onClick={() => exportCSV(result)}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  <Download className="w-3.5 h-3.5" />
                  Export CSV
                </motion.button>
              </div>
              <div className="max-h-96 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card border-b border-border">
                    <tr className="text-xs text-muted-foreground">
                      <th className="text-left p-3 font-medium">Timestamp</th>
                      <th className="text-right p-3 font-medium">Predicted (MW)</th>
                      <th className="text-right p-3 font-medium">Lower Bound</th>
                      <th className="text-right p-3 font-medium">Upper Bound</th>
                      <th className="text-right p-3 font-medium">Spread</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.timestamps.map((t: string, i: number) => {
                      const isPeak = result.predicted_mw[i] === peak;
                      const isTrough = result.predicted_mw[i] === trough;
                      return (
                        <tr
                          key={i}
                          className={`border-b border-border/50 transition-colors ${
                            isPeak ? "bg-amber-500/5" : isTrough ? "bg-blue-500/5" : "hover:bg-accent/30"
                          }`}
                        >
                          <td className="p-3 font-mono text-xs">
                            {new Date(t).toLocaleString("en-IN")}
                            {isPeak && <Badge className="ml-2 text-[9px] bg-amber-500/20 text-amber-400 border-0">PEAK</Badge>}
                            {isTrough && <Badge className="ml-2 text-[9px] bg-blue-500/20 text-blue-400 border-0">MIN</Badge>}
                          </td>
                          <td className={`p-3 text-right font-mono font-medium ${isPeak ? "text-amber-400" : isTrough ? "text-blue-400" : ""}`}>
                            {result.predicted_mw[i].toFixed(1)}
                          </td>
                          <td className="p-3 text-right font-mono text-muted-foreground">{result.lower_bound_mw[i].toFixed(1)}</td>
                          <td className="p-3 text-right font-mono text-muted-foreground">{result.upper_bound_mw[i].toFixed(1)}</td>
                          <td className="p-3 text-right font-mono text-xs text-muted-foreground">
                            {(result.upper_bound_mw[i] - result.lower_bound_mw[i]).toFixed(0)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Empty State */}
      {!result && !loading && !error && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="flex items-center justify-center h-[300px] rounded-xl border border-dashed border-border"
        >
          <div className="text-center space-y-3">
            <Zap className="w-12 h-12 text-muted-foreground/20 mx-auto" />
            <div>
              <p className="text-sm text-muted-foreground">Select a date and resolution to generate a forecast</p>
              <p className="text-xs text-muted-foreground/60 mt-1">
                Supports past dates (backtesting) and up to 90 days into the future
              </p>
            </div>
          </div>
        </motion.div>
      )}
    </div>
  );
}
