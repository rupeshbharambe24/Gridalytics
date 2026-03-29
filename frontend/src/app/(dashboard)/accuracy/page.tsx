"use client";

import { motion } from "framer-motion";
import { Target, TrendingUp, TrendingDown, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useFetch } from "@/lib/hooks";
import {
  ResponsiveContainer, LineChart, Line, AreaChart, Area, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ReferenceLine, Cell,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function fetchHistory(days: number) {
  return fetch(`${API}/api/v1/dashboard/prediction-history?days=${days}`).then(r => r.json());
}
function fetchTrend(days: number) {
  return fetch(`${API}/api/v1/dashboard/accuracy-trend?days=${days}`).then(r => r.json());
}

export default function AccuracyPage() {
  const { data: history } = useFetch(() => fetchHistory(60), []);
  const { data: trend } = useFetch(() => fetchTrend(60), []);

  const entries = history?.entries || [];
  const withActuals = entries.filter((e: any) => e.actual_peak !== null);
  const summary = history?.summary || {};

  // Chart data: predicted vs actual
  const comparisonData = withActuals.map((e: any) => ({
    date: e.date.slice(5),  // MM-DD
    predicted: Math.round(e.predicted_peak),
    actual: Math.round(e.actual_peak),
    error: Math.round(e.peak_error || 0),
    mape: e.mape?.toFixed(1),
  }));

  // MAPE trend chart data
  const trendData = (trend?.dates || []).map((d: string, i: number) => ({
    date: d.slice(5),
    daily: trend.daily_mape?.[i],
    rolling7d: trend.rolling_7d_mape?.[i],
    rolling30d: trend.rolling_30d_mape?.[i],
  }));

  // Error distribution
  const errorBuckets: Record<string, number> = {};
  withActuals.forEach((e: any) => {
    const err = Math.abs(e.peak_error || 0);
    const bucket = err < 50 ? "<50" : err < 100 ? "50-100" : err < 200 ? "100-200" : err < 300 ? "200-300" : ">300";
    errorBuckets[bucket] = (errorBuckets[bucket] || 0) + 1;
  });
  const errorDist = Object.entries(errorBuckets).map(([bucket, count]) => ({ bucket: bucket + " MW", count }));

  const driftStatus = trend?.drift_status || "stable";

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Prediction Accuracy</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Daily predicted vs actual demand tracking</p>
      </motion.div>

      {/* KPI Row */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        {[
          { label: "Avg MAPE", value: summary.avg_mape ? `${summary.avg_mape}%` : "---", color: "text-blue-400" },
          { label: "Avg MAE", value: summary.avg_mae ? `${summary.avg_mae} MW` : "---", color: "text-emerald-400" },
          { label: "Days Tracked", value: summary.days_with_actuals || 0, color: "text-foreground" },
          { label: "Best Day", value: summary.best_day ? `${summary.best_day[1]}%` : "---", color: "text-emerald-400" },
          { label: "Drift Status", value: driftStatus, color: driftStatus === "stable" ? "text-emerald-400" : "text-amber-400", icon: driftStatus === "stable" ? CheckCircle2 : AlertTriangle },
        ].map((item, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-xl border border-border bg-card p-4"
          >
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider">{item.label}</p>
            <p className={`text-xl font-bold font-mono mt-1 ${item.color}`}>{item.value}</p>
          </motion.div>
        ))}
      </div>

      {/* Predicted vs Actual Chart */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2 }}
        className="rounded-xl border border-border bg-card p-5"
      >
        <h3 className="text-sm font-semibold mb-4">Predicted vs Actual Peak Demand</h3>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={comparisonData}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
            <Tooltip
              contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "12px" }}
              formatter={(val: any, name: any) => [`${val} MW`, name]}
            />
            <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 10 }} />
            <Line type="monotone" dataKey="actual" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} name="Actual Peak" />
            <Line type="monotone" dataKey="predicted" stroke="#f59e0b" strokeWidth={2} strokeDasharray="5 3" dot={{ r: 3 }} name="Predicted Peak" />
          </LineChart>
        </ResponsiveContainer>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* MAPE Trend */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl border border-border bg-card p-5"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold">MAPE Trend (Drift Detection)</h3>
            <Badge
              variant="outline"
              className={driftStatus === "stable" ? "text-emerald-400 border-emerald-500/30" : "text-amber-400 border-amber-500/30"}
            >
              {driftStatus}
            </Badge>
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={trendData}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "12px" }} />
              <ReferenceLine y={trend?.threshold || 5} stroke="#ef4444" strokeDasharray="5 5" label={{ value: "Alert Threshold", fontSize: 10, fill: "#ef4444" }} />
              <Area type="monotone" dataKey="daily" stroke="#6b7280" strokeWidth={1} fill="none" name="Daily MAPE %" dot={false} />
              <Area type="monotone" dataKey="rolling7d" stroke="#3b82f6" strokeWidth={2} fill="rgba(59,130,246,0.1)" name="7-Day Rolling" dot={false} />
              <Area type="monotone" dataKey="rolling30d" stroke="#f59e0b" strokeWidth={2} fill="rgba(245,158,11,0.05)" name="30-Day Rolling" dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </motion.div>

        {/* Error Distribution */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="rounded-xl border border-border bg-card p-5"
        >
          <h3 className="text-sm font-semibold mb-4">Peak Error Distribution</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={errorDist}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis dataKey="bucket" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px" }} />
              <Bar dataKey="count" name="Days" radius={[6, 6, 0, 0]}>
                {errorDist.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? "#10b981" : i === 1 ? "#3b82f6" : i === 2 ? "#f59e0b" : "#ef4444"} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      </div>

      {/* Detailed Log Table */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="p-4 border-b border-border">
          <h3 className="text-sm font-semibold">Prediction Log (Last 60 Days)</h3>
        </div>
        <div className="max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-card border-b border-border">
              <tr className="text-xs text-muted-foreground">
                <th className="text-left p-3 font-medium">Date</th>
                <th className="text-right p-3 font-medium">Predicted Peak</th>
                <th className="text-right p-3 font-medium">Actual Peak</th>
                <th className="text-right p-3 font-medium">Error</th>
                <th className="text-right p-3 font-medium">MAPE</th>
                <th className="text-left p-3 font-medium">Notes</th>
              </tr>
            </thead>
            <tbody>
              {withActuals.map((e: any, i: number) => (
                <tr key={i} className="border-b border-border/50 hover:bg-accent/20 transition-colors">
                  <td className="p-3 font-mono text-xs">{e.date}</td>
                  <td className="p-3 text-right font-mono">{e.predicted_peak?.toFixed(0)} MW</td>
                  <td className="p-3 text-right font-mono font-medium">{e.actual_peak?.toFixed(0)} MW</td>
                  <td className={`p-3 text-right font-mono ${(e.peak_error || 0) > 0 ? "text-amber-400" : "text-blue-400"}`}>
                    {e.peak_error ? `${e.peak_error > 0 ? "+" : ""}${e.peak_error.toFixed(0)}` : "---"}
                  </td>
                  <td className="p-3 text-right">
                    <span className={`font-mono ${(e.mape || 0) < 2 ? "text-emerald-400" : (e.mape || 0) < 5 ? "text-amber-400" : "text-rose-400"}`}>
                      {e.mape?.toFixed(1)}%
                    </span>
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">{e.notes || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  );
}
