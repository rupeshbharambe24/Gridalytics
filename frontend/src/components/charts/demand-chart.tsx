"use client";

import { motion } from "framer-motion";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ReferenceLine,
} from "recharts";

interface DemandChartProps {
  data: { time: string; demand: number | null; temperature?: number | null }[];
  title?: string;
  showTemp?: boolean;
  height?: number;
  forecast?: { time: string; predicted: number; lower: number; upper: number }[];
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-card/95 backdrop-blur-sm border border-border rounded-lg px-3 py-2 shadow-xl">
      <p className="text-xs text-muted-foreground mb-1">{label}</p>
      {payload.map((p: any) => (
        <p key={p.name} className="text-sm font-medium" style={{ color: p.color }}>
          {p.name}: <span className="font-mono">{p.value?.toFixed(1)}</span>
          {p.name.includes("Demand") || p.name.includes("MW") ? " MW" : p.name.includes("Temp") ? "°C" : ""}
        </p>
      ))}
    </div>
  );
}

export function DemandChart({ data, title, showTemp = false, height = 350, forecast }: DemandChartProps) {
  const mergedData = data.map((d) => {
    const f = forecast?.find((f) => f.time === d.time);
    return { ...d, predicted: f?.predicted, lower: f?.lower, upper: f?.upper };
  });

  // Append forecast-only data points
  if (forecast) {
    forecast.forEach((f) => {
      if (!data.find((d) => d.time === f.time)) {
        mergedData.push({ time: f.time, demand: null, predicted: f.predicted, lower: f.lower, upper: f.upper });
      }
    });
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="rounded-xl border border-border bg-card p-5"
    >
      {title && <h3 className="text-sm font-semibold text-foreground mb-4">{title}</h3>}
      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={mergedData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <defs>
            <linearGradient id="demandGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#f59e0b" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#f59e0b" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="tempGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.3} />
          <XAxis
            dataKey="time"
            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
            axisLine={{ stroke: "hsl(var(--border))" }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
            axisLine={false}
            tickLine={false}
            width={60}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend
            wrapperStyle={{ fontSize: 12, paddingTop: 10 }}
            iconType="circle"
            iconSize={8}
          />

          {forecast && (
            <Area
              type="monotone"
              dataKey="upper"
              stroke="none"
              fill="#f59e0b"
              fillOpacity={0.08}
              name="Confidence Band"
            />
          )}
          {forecast && (
            <Area
              type="monotone"
              dataKey="lower"
              stroke="none"
              fill="transparent"
              name=" "
            />
          )}

          <Area
            type="monotone"
            dataKey="demand"
            stroke="#3b82f6"
            strokeWidth={2}
            fill="url(#demandGrad)"
            name="Actual Demand"
            dot={false}
            connectNulls={false}
          />

          {forecast && (
            <Area
              type="monotone"
              dataKey="predicted"
              stroke="#f59e0b"
              strokeWidth={2}
              strokeDasharray="6 3"
              fill="url(#forecastGrad)"
              name="Forecast"
              dot={false}
            />
          )}

          {showTemp && (
            <Area
              type="monotone"
              dataKey="temperature"
              stroke="#10b981"
              strokeWidth={1.5}
              fill="url(#tempGrad)"
              name="Temperature"
              dot={false}
              yAxisId="right"
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </motion.div>
  );
}
