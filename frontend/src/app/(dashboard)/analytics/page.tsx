"use client";

import { motion } from "framer-motion";
import { LineChart, BarChart3, TrendingUp } from "lucide-react";
import { DemandChart } from "@/components/charts/demand-chart";
import { HeatmapChart } from "@/components/charts/heatmap-chart";
import { useFetch } from "@/lib/hooks";
import { getHistorical, getHeatmap, getStats } from "@/lib/api";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";

const seasonColors: Record<string, string> = {
  Winter: "#3b82f6",
  Spring: "#10b981",
  Summer: "#f59e0b",
  Monsoon: "#8b5cf6",
  Autumn: "#ef4444",
};

export default function AnalyticsPage() {
  const { data: monthly } = useFetch(() => getHistorical(90, "daily"));
  const { data: weekly } = useFetch(() => getHistorical(30, "hourly"));
  const { data: heatmap } = useFetch(() => getHeatmap(60));
  const { data: stats } = useFetch(getStats);

  const monthlyChart = monthly?.timestamps.map((t, i) => ({
    time: new Date(t).toLocaleDateString("en-IN", { month: "short", day: "numeric" }),
    demand: monthly.demand_mw[i],
    temperature: monthly.temperature?.[i],
  })) || [];

  const weeklyChart = weekly?.timestamps.map((t, i) => ({
    time: new Date(t).toLocaleString("en-IN", { month: "short", day: "numeric", hour: "2-digit" }),
    demand: weekly.demand_mw[i],
  })) || [];

  // Compute daily averages for bar chart
  const dailyAvg: { day: string; avg: number; season: string }[] = [];
  if (monthly) {
    const byDay: Record<string, number[]> = {};
    monthly.timestamps.forEach((t, i) => {
      const d = new Date(t).toLocaleDateString("en-IN", { month: "short", day: "numeric" });
      if (!byDay[d]) byDay[d] = [];
      if (monthly.demand_mw[i]) byDay[d].push(monthly.demand_mw[i]!);
    });
    Object.entries(byDay).forEach(([day, vals]) => {
      const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
      const month = new Date(day + " 2026").getMonth() + 1;
      const season = [11, 12, 1, 2].includes(month) ? "Winter" : [3, 4].includes(month) ? "Spring" : [5, 6].includes(month) ? "Summer" : [7, 8, 9].includes(month) ? "Monsoon" : "Autumn";
      dailyAvg.push({ day, avg, season });
    });
  }

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Historical demand patterns and trends</p>
      </motion.div>

      {/* 90-Day Trend */}
      <DemandChart
        data={monthlyChart}
        title="Demand Trend - Last 90 Days (Daily)"
        showTemp
        height={320}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Daily Average Bar Chart */}
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-xl border border-border bg-card p-5"
        >
          <h3 className="text-sm font-semibold text-foreground mb-4">Daily Average Demand (Color = Season)</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={dailyAvg.slice(-30)}>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
              <XAxis
                dataKey="day"
                tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }}
                tickLine={false}
                axisLine={false}
                interval={4}
              />
              <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                  fontSize: "12px",
                }}
              />
              <Bar dataKey="avg" radius={[4, 4, 0, 0]} name="Avg Demand (MW)">
                {dailyAvg.slice(-30).map((entry, i) => (
                  <Cell key={i} fill={seasonColors[entry.season] || "#6b7280"} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <div className="flex gap-4 mt-2 justify-center">
            {Object.entries(seasonColors).map(([season, color]) => (
              <div key={season} className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
                {season}
              </div>
            ))}
          </div>
        </motion.div>

        {/* Heatmap */}
        {heatmap && (
          <HeatmapChart hours={heatmap.hours} days={heatmap.days} values={heatmap.values} />
        )}
      </div>

      {/* Quick Stats */}
      {stats && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="grid grid-cols-2 md:grid-cols-4 gap-4"
        >
          {[
            { label: "Current Season", value: stats.season, icon: "🌤️" },
            { label: "Demand Trend", value: stats.demand_trend, icon: stats.demand_trend === "rising" ? "📈" : "📉" },
            { label: "This Week Avg", value: stats.this_week_avg ? `${stats.this_week_avg.toFixed(0)} MW` : "---" },
            { label: "Last Week Avg", value: stats.last_week_avg ? `${stats.last_week_avg.toFixed(0)} MW` : "---" },
          ].map((item, i) => (
            <div key={i} className="rounded-lg border border-border bg-card/50 p-4">
              <p className="text-xs text-muted-foreground">{item.label}</p>
              <p className="text-lg font-semibold text-foreground mt-1">{item.value}</p>
            </div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
