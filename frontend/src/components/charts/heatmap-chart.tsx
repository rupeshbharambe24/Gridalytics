"use client";

import { motion } from "framer-motion";

interface HeatmapChartProps {
  hours: number[];
  days: string[];
  values: number[][];
}

function getColor(value: number, min: number, max: number) {
  const t = max === min ? 0.5 : (value - min) / (max - min);
  // Dark blue → cyan → green → yellow → red
  if (t < 0.25) return `rgba(59, 130, 246, ${0.2 + t * 2})`;
  if (t < 0.5) return `rgba(16, 185, 129, ${0.3 + (t - 0.25) * 2})`;
  if (t < 0.75) return `rgba(245, 158, 11, ${0.4 + (t - 0.5) * 2})`;
  return `rgba(239, 68, 68, ${0.5 + (t - 0.75) * 2})`;
}

export function HeatmapChart({ hours, days, values }: HeatmapChartProps) {
  const allValues = values.flat();
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="rounded-xl border border-border bg-card p-5"
    >
      <h3 className="text-sm font-semibold text-foreground mb-4">Demand Heatmap (Hour x Day)</h3>
      <div className="overflow-x-auto">
        <div className="min-w-[600px]">
          {/* Header row */}
          <div className="flex">
            <div className="w-20 shrink-0" />
            {hours.map((h) => (
              <div key={h} className="flex-1 text-center text-[10px] text-muted-foreground font-mono pb-1">
                {h.toString().padStart(2, "0")}
              </div>
            ))}
          </div>
          {/* Data rows */}
          {days.map((day, di) => (
            <div key={day} className="flex items-center">
              <div className="w-20 shrink-0 text-xs text-muted-foreground pr-2 text-right">
                {day.slice(0, 3)}
              </div>
              <div className="flex flex-1 gap-px">
                {(values[di] || []).map((val, hi) => (
                  <motion.div
                    key={hi}
                    initial={{ opacity: 0, scale: 0.5 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ duration: 0.3, delay: (di * 24 + hi) * 0.002 }}
                    className="flex-1 aspect-square rounded-sm cursor-pointer transition-transform hover:scale-110 hover:z-10 relative group"
                    style={{ backgroundColor: getColor(val, min, max) }}
                    title={`${day} ${hours[hi]}:00 — ${val.toFixed(0)} MW`}
                  >
                    <div className="absolute -top-8 left-1/2 -translate-x-1/2 bg-card border border-border rounded px-1.5 py-0.5 text-[10px] font-mono text-foreground opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-20 shadow-lg">
                      {val.toFixed(0)} MW
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ))}
          {/* Legend */}
          <div className="flex items-center justify-end gap-2 mt-3 pr-1">
            <span className="text-[10px] text-muted-foreground">{min.toFixed(0)} MW</span>
            <div className="flex h-2 w-32 rounded-full overflow-hidden">
              <div className="flex-1 bg-blue-500/50" />
              <div className="flex-1 bg-emerald-500/50" />
              <div className="flex-1 bg-amber-500/50" />
              <div className="flex-1 bg-red-500/50" />
            </div>
            <span className="text-[10px] text-muted-foreground">{max.toFixed(0)} MW</span>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
