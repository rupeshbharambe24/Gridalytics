"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Zap, Thermometer, Activity, Award, Clock, RefreshCw } from "lucide-react";
import { KPICard } from "@/components/dashboard/kpi-card";
import { DemandChart } from "@/components/charts/demand-chart";
import { HeatmapChart } from "@/components/charts/heatmap-chart";
import { Badge } from "@/components/ui/badge";
import { getLive, getHistorical, getHeatmap, getStats } from "@/lib/api";
import { useFetch } from "@/lib/hooks";

export default function DashboardPage() {
  const { data: live, loading: liveLoading, refetch: refetchLive } = useFetch(getLive);
  const { data: stats } = useFetch(getStats);
  const { data: historical } = useFetch(() => getHistorical(7, "hourly"));
  const { data: heatmap } = useFetch(() => getHeatmap(30));

  // Auto-refresh live data every 5 minutes
  useEffect(() => {
    const interval = setInterval(refetchLive, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [refetchLive]);

  const chartData = historical?.timestamps.map((t, i) => ({
    time: new Date(t).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit" }),
    demand: historical.demand_mw[i],
    temperature: historical.temperature?.[i],
  })) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        className="flex items-center justify-between"
      >
        <div>
          <h1 className="text-2xl font-bold text-foreground tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Delhi Power Grid — Real-time demand monitoring
          </p>
        </div>
        <div className="flex items-center gap-3">
          {stats && (
            <Badge variant="outline" className="text-xs gap-1.5 px-3 py-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              {stats.season} Season
            </Badge>
          )}
          <button
            onClick={refetchLive}
            className="p-2 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${liveLoading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </motion.div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <KPICard
          title="Current Demand"
          value={live?.current_demand_mw?.toFixed(0) ?? null}
          unit="MW"
          subtitle={live?.timestamp ? `Updated ${new Date(live.timestamp).toLocaleTimeString("en-IN")}` : undefined}
          trend={live?.vs_yesterday_pct}
          icon={Zap}
          color="blue"
          delay={0}
        />
        <KPICard
          title="Today's Peak"
          value={live?.today_peak_mw?.toFixed(0) ?? stats?.yesterday.peak?.toFixed(0) ?? null}
          unit="MW"
          subtitle={live?.today_peak_time ? `at ${live.today_peak_time}` : stats?.yesterday.peak ? "Yesterday's peak" : undefined}
          icon={Activity}
          color="amber"
          delay={0.1}
        />
        <KPICard
          title="Temperature"
          value={live?.weather?.temperature?.toFixed(1) ?? null}
          unit="°C"
          subtitle={live?.weather?.humidity ? `Humidity: ${live.weather.humidity.toFixed(0)}%` : undefined}
          icon={Thermometer}
          color="emerald"
          delay={0.2}
        />
        <KPICard
          title="Model Accuracy"
          value="99.5"
          unit="% R²"
          subtitle="XGBoost (hourly)"
          icon={Award}
          color="violet"
          delay={0.3}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <DemandChart
            data={chartData}
            title="Demand — Last 7 Days (Hourly)"
            showTemp
          />
        </div>
        <div>
          {heatmap && (
            <HeatmapChart
              hours={heatmap.hours}
              days={heatmap.days}
              values={heatmap.values}
            />
          )}
        </div>
      </div>

      {/* Stats Bar */}
      {stats && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          {[
            { label: "This Week Avg", value: stats.this_week_avg, unit: "MW" },
            { label: "Last Week Avg", value: stats.last_week_avg, unit: "MW" },
            { label: "Trend", value: stats.demand_trend, isText: true },
            { label: "Season", value: stats.season, isText: true },
          ].map((item, i) => (
            <div key={i} className="rounded-lg border border-border bg-card/50 p-4">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="text-lg font-semibold text-foreground mt-1 font-mono">
                {item.isText
                  ? (item.value as string)
                  : item.value
                    ? `${(item.value as number).toFixed(0)} ${item.unit}`
                    : "---"}
              </p>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
