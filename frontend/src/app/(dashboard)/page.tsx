"use client";

import { useEffect } from "react";
import { motion } from "framer-motion";
import { Zap, Thermometer, Activity, Award, RefreshCw } from "lucide-react";
import { KPICard } from "@/components/dashboard/kpi-card";
import { KPISkeletons, ChartSkeleton } from "@/components/dashboard/skeleton-cards";
import { DemandChart } from "@/components/charts/demand-chart";
import { HeatmapChart } from "@/components/charts/heatmap-chart";
import { Badge } from "@/components/ui/badge";
import { getLive, getHistorical, getHeatmap, getStats, getModelPerformance, getPredictionHistory, getSubregionForecast } from "@/lib/api";
import { useFetch } from "@/lib/hooks";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";

export default function DashboardPage() {
  const { data: live, loading: liveLoading, refetch: refetchLive } = useFetch(getLive);
  const { data: stats, loading: statsLoading } = useFetch(getStats);
  const { data: modelPerf } = useFetch(getModelPerformance);
  const { data: historical, loading: histLoading } = useFetch(() => getHistorical(7, "hourly"));
  const { data: heatmap, loading: heatLoading } = useFetch(() => getHeatmap(30));
  const { data: predHistory } = useFetch(() => getPredictionHistory(14));
  const { data: subregions } = useFetch(() => {
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    return getSubregionForecast("hourly", yesterday.toISOString().split("T")[0]);
  });

  useEffect(() => {
    const interval = setInterval(refetchLive, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [refetchLive]);

  const chartData = historical?.timestamps.map((t, i) => ({
    time: new Date(t).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit" }),
    demand: historical.demand_mw[i],
    temperature: historical.temperature?.[i],
  })) || [];

  // Accuracy mini-chart data
  const accuracyData = (predHistory?.entries || [])
    .filter((e: any) => e.actual_peak && e.predicted_peak)
    .slice(-10)
    .map((e: any) => ({
      date: e.date?.slice(5),
      predicted: Math.round(e.predicted_peak),
      actual: Math.round(e.actual_peak),
    }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">Delhi Power Grid — Real-time demand monitoring</p>
        </div>
        <div className="flex items-center gap-3">
          {/* Data freshness indicator */}
          {live?.timestamp && (
            <Badge variant="outline" className={`text-[10px] gap-1 px-2 py-0.5 hidden md:flex ${
              (Date.now() - new Date(live.timestamp).getTime()) > 12 * 3600000 ? "text-amber-400 border-amber-500/30" : "text-emerald-400 border-emerald-500/30"
            }`}>
              <span className={`w-1.5 h-1.5 rounded-full ${
                (Date.now() - new Date(live.timestamp).getTime()) > 12 * 3600000 ? "bg-amber-400" : "bg-emerald-400 animate-pulse"
              }`} />
              Data: {Math.round((Date.now() - new Date(live.timestamp).getTime()) / 3600000)}h ago
            </Badge>
          )}
          {stats && (
            <Badge variant="outline" className="text-xs gap-1.5 px-3 py-1 hidden sm:flex">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {stats.season} Season
            </Badge>
          )}
          <button onClick={refetchLive}
            className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors">
            <RefreshCw className={`w-4 h-4 ${liveLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </motion.div>

      {/* KPI Cards with skeleton loading */}
      {liveLoading && !live ? (
        <KPISkeletons />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard
            title="Current Demand"
            value={live?.current_demand_mw?.toFixed(0) ?? null}
            unit="MW"
            subtitle={
              live?.forecast_1h_mw
                ? `1h forecast: ${live.forecast_1h_mw.toFixed(0)} MW [${live.forecast_1h_lower?.toFixed(0)}-${live.forecast_1h_upper?.toFixed(0)}]`
                : live?.timestamp ? `Updated ${new Date(live.timestamp).toLocaleTimeString("en-IN")}` : undefined
            }
            trend={live?.vs_yesterday_pct}
            icon={Zap} color="blue" delay={0}
          />
          <KPICard
            title="Today's Peak"
            value={live?.today_peak_mw?.toFixed(0) ?? stats?.yesterday.peak?.toFixed(0) ?? null}
            unit="MW"
            subtitle={live?.today_peak_time ? `at ${live.today_peak_time}` : stats?.yesterday.peak ? "Yesterday's peak" : undefined}
            icon={Activity} color="amber" delay={0.1}
          />
          <KPICard
            title="Temperature"
            value={live?.weather?.temperature?.toFixed(1) ?? null}
            unit="°C"
            subtitle={live?.weather?.humidity ? `Humidity: ${live.weather.humidity.toFixed(0)}%` : undefined}
            icon={Thermometer} color="emerald" delay={0.2}
          />
          <KPICard
            title="Model Accuracy"
            value={modelPerf?.champion?.hourly_mape?.toFixed(2) ?? null}
            unit="% MAPE"
            subtitle={modelPerf?.champion?.name ? `${modelPerf.champion.name} | ${modelPerf.champion.tracked_days || 0} days tracked` : undefined}
            icon={Award} color="violet" delay={0.3}
          />
        </div>
      )}

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          {histLoading && !historical ? (
            <ChartSkeleton />
          ) : (
            <DemandChart data={chartData} title="Demand — Last 7 Days (Hourly)" showTemp />
          )}
        </div>
        <div>
          {heatLoading && !heatmap ? (
            <ChartSkeleton height={300} />
          ) : heatmap ? (
            <HeatmapChart hours={heatmap.hours} days={heatmap.days} values={heatmap.values} />
          ) : null}
        </div>
      </div>

      {/* Sub-Regional / DISCOM Breakdown */}
      {subregions?.regions && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
          className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-4">
            DISCOM Breakdown — {subregions.date || "Yesterday"} (Peak MW)
          </h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={Object.entries(subregions.regions)
                .filter(([k]) => k !== "delhi")
                .map(([name, data]: [string, any]) => ({
                  name: name.toUpperCase(),
                  peak: data.peak_mw || 0,
                  avg: data.avg_mw || 0,
                }))}
              layout="vertical"
            >
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
              <YAxis dataKey="name" type="category" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} width={55} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "12px" }} />
              <Bar dataKey="peak" name="Peak MW" fill="#f59e0b" radius={[0, 4, 4, 0]} opacity={0.8} />
              <Bar dataKey="avg" name="Avg MW" fill="#3b82f6" radius={[0, 4, 4, 0]} opacity={0.6} />
            </BarChart>
          </ResponsiveContainer>
          <div className="grid grid-cols-3 md:grid-cols-6 gap-2 mt-3">
            {Object.entries(subregions.regions).map(([name, data]: [string, any]) => (
              <div key={name} className="rounded-lg bg-accent/30 p-2 text-center">
                <p className="text-[10px] text-muted-foreground uppercase">{name}</p>
                <p className="text-sm font-bold font-mono text-foreground">{data.peak_mw?.toFixed(0) || "---"}</p>
                <p className="text-[10px] text-muted-foreground">MW peak</p>
              </div>
            ))}
          </div>
        </motion.div>
      )}

      {/* Accuracy Mini-Chart (Predicted vs Actual - last 10 days) */}
      {accuracyData.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
          className="rounded-xl border border-border bg-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-4">Prediction Accuracy — Last 10 Days (Peak MW)</h3>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={accuracyData} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <Tooltip contentStyle={{ backgroundColor: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: "8px", fontSize: "12px" }} />
              <Bar dataKey="actual" name="Actual Peak" fill="#3b82f6" radius={[4, 4, 0, 0]} opacity={0.7} />
              <Bar dataKey="predicted" name="Predicted Peak" fill="#f59e0b" radius={[4, 4, 0, 0]} opacity={0.7} />
            </BarChart>
          </ResponsiveContainer>
        </motion.div>
      )}

      {/* Stats Bar */}
      {stats && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.4 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: "This Week Avg", value: stats.this_week_avg, unit: "MW" },
            { label: "Last Week Avg", value: stats.last_week_avg, unit: "MW" },
            { label: "Trend", value: stats.demand_trend, isText: true },
            { label: "Season", value: stats.season, isText: true },
          ].map((item, i) => (
            <div key={i} className="rounded-lg border border-border bg-card/50 p-4">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="text-lg font-semibold text-foreground mt-1 font-mono">
                {item.isText ? (item.value as string) : item.value ? `${(item.value as number).toFixed(0)} ${item.unit}` : "---"}
              </p>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
