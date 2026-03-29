"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { TrendingUp, Calendar, Loader2, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { DemandChart } from "@/components/charts/demand-chart";
import { getForecast } from "@/lib/api";

export default function ForecastPage() {
  const [resolution, setResolution] = useState<"daily" | "hourly">("hourly");
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getForecast(resolution, date);
      setResult(data);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const chartData = result
    ? result.timestamps.map((t: string, i: number) => ({
        time: resolution === "hourly"
          ? new Date(t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
          : new Date(t).toLocaleDateString("en-IN", { month: "short", day: "numeric" }),
        demand: result.predicted_mw[i],
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Forecast</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Predict electricity demand for any date</p>
      </motion.div>

      {/* Controls */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="flex flex-wrap items-end gap-4 p-5 rounded-xl border border-border bg-card"
      >
        {/* Resolution Toggle */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Resolution</label>
          <div className="flex rounded-lg border border-border overflow-hidden">
            {(["daily", "hourly"] as const).map((r) => (
              <button
                key={r}
                onClick={() => setResolution(r)}
                className={`px-4 py-2 text-sm font-medium transition-colors ${
                  resolution === r
                    ? "bg-blue-600 text-white"
                    : "bg-card text-muted-foreground hover:text-foreground"
                }`}
              >
                {r.charAt(0).toUpperCase() + r.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Date Picker */}
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">Date</label>
          <div className="relative">
            <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="pl-10 w-48 bg-background"
            />
          </div>
        </div>

        {/* Predict Button */}
        <motion.button
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={handlePredict}
          disabled={loading}
          className="flex items-center gap-2 px-6 py-2 rounded-lg bg-blue-600 text-white font-medium text-sm hover:bg-blue-500 disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
          Predict
        </motion.button>
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
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            {/* Summary Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="rounded-xl border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Peak Demand</p>
                <div className="flex items-center gap-1.5 mt-1">
                  <ArrowUpRight className="w-4 h-4 text-amber-400" />
                  <span className="text-xl font-bold font-mono">{peak?.toFixed(0)}</span>
                  <span className="text-sm text-muted-foreground">MW</span>
                </div>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Minimum</p>
                <div className="flex items-center gap-1.5 mt-1">
                  <ArrowDownRight className="w-4 h-4 text-blue-400" />
                  <span className="text-xl font-bold font-mono">{trough?.toFixed(0)}</span>
                  <span className="text-sm text-muted-foreground">MW</span>
                </div>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Average</p>
                <span className="text-xl font-bold font-mono mt-1 block">{avg?.toFixed(0)} MW</span>
              </div>
              <div className="rounded-xl border border-border bg-card p-4">
                <p className="text-xs text-muted-foreground">Model</p>
                <div className="flex items-center gap-2 mt-1">
                  <Badge variant="outline" className="text-xs">{result.model_name}</Badge>
                  <span className="text-xs text-muted-foreground">{result.predicted_mw.length} pts</span>
                </div>
              </div>
            </div>

            {/* Chart */}
            <DemandChart
              data={chartData}
              forecast={forecastData}
              title={`${resolution === "hourly" ? "Hourly" : "Daily"} Forecast — ${date}`}
              height={400}
            />

            {/* Data Table */}
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 bg-card border-b border-border">
                    <tr className="text-xs text-muted-foreground">
                      <th className="text-left p-3 font-medium">Time</th>
                      <th className="text-right p-3 font-medium">Predicted (MW)</th>
                      <th className="text-right p-3 font-medium">Lower</th>
                      <th className="text-right p-3 font-medium">Upper</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.timestamps.map((t: string, i: number) => (
                      <tr key={i} className="border-b border-border/50 hover:bg-accent/30 transition-colors">
                        <td className="p-3 font-mono text-xs">{new Date(t).toLocaleString("en-IN")}</td>
                        <td className="p-3 text-right font-mono font-medium">{result.predicted_mw[i].toFixed(1)}</td>
                        <td className="p-3 text-right font-mono text-muted-foreground">{result.lower_bound_mw[i].toFixed(1)}</td>
                        <td className="p-3 text-right font-mono text-muted-foreground">{result.upper_bound_mw[i].toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
