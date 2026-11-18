"use client";

import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { LucideIcon, TrendingUp, TrendingDown, Minus } from "lucide-react";

interface KPICardProps {
  title: string;
  value: string | number | null;
  unit?: string;
  subtitle?: string;
  trend?: number | null;
  icon: LucideIcon;
  color?: "brand" | "blue" | "emerald" | "amber" | "rose" | "violet";
  delay?: number;
  sparkline?: (number | null)[];
}

const COLORS: Record<string, { chip: string; stroke: string; glow: string }> = {
  brand:   { chip: "bg-brand/15 text-brand",        stroke: "hsl(var(--brand))",          glow: "hsl(var(--brand))" },
  blue:    { chip: "bg-blue-500/15 text-blue-400",  stroke: "#3b82f6", glow: "#3b82f6" },
  emerald: { chip: "bg-emerald-500/15 text-emerald-400", stroke: "#10b981", glow: "#10b981" },
  amber:   { chip: "bg-amber-500/15 text-amber-400", stroke: "#f59e0b", glow: "#f59e0b" },
  rose:    { chip: "bg-rose-500/15 text-rose-400",  stroke: "#f43f5e", glow: "#f43f5e" },
  violet:  { chip: "bg-violet-500/15 text-violet-400", stroke: "#8b5cf6", glow: "#8b5cf6" },
};

function Sparkline({ data, stroke }: { data: (number | null)[]; stroke: string }) {
  const pts = data.filter((d): d is number => d != null);
  if (pts.length < 2) return null;
  const min = Math.min(...pts), max = Math.max(...pts);
  const span = max - min || 1;
  const w = 100, h = 28;
  const step = w / (pts.length - 1);
  const d = pts
    .map((v, i) => `${i === 0 ? "M" : "L"}${(i * step).toFixed(1)},${(h - ((v - min) / span) * h).toFixed(1)}`)
    .join(" ");
  const gid = `spark-${stroke.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-7 mt-3" aria-hidden>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.25} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      <path d={`${d} L${w},${h} L0,${h} Z`} fill={`url(#${gid})`} />
      <path d={d} fill="none" stroke={stroke} strokeWidth={1.8} strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function KPICard({ title, value, unit, subtitle, trend, icon: Icon, color = "brand", delay = 0, sparkline }: KPICardProps) {
  const c = COLORS[color] ?? COLORS.brand;
  const TrendIcon = trend && trend > 0 ? TrendingUp : trend && trend < 0 ? TrendingDown : Minus;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={{ y: -2 }}
      className="group relative overflow-hidden rounded-xl border border-border bg-card p-5 shadow-card transition-shadow hover:shadow-brand"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2 min-w-0">
          <p className="text-[11px] font-medium text-muted-foreground uppercase tracking-wider truncate">{title}</p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold text-foreground font-mono tabular-nums">
              {value ?? "—"}
            </span>
            {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
          </div>
          {subtitle && <p className="text-xs text-muted-foreground truncate">{subtitle}</p>}
        </div>
        <div className={cn("p-2.5 rounded-lg shrink-0", c.chip)}>
          <Icon className="w-5 h-5" />
        </div>
      </div>

      {trend !== undefined && trend !== null && (
        <div className="mt-3 flex items-center gap-1.5">
          <TrendIcon className={cn("w-3.5 h-3.5", trend > 0 ? "text-emerald-400" : trend < 0 ? "text-rose-400" : "text-muted-foreground")} />
          <span className={cn("text-xs font-medium", trend > 0 ? "text-emerald-400" : trend < 0 ? "text-rose-400" : "text-muted-foreground")}>
            {trend > 0 ? "+" : ""}{trend.toFixed(1)}% vs yesterday
          </span>
        </div>
      )}

      {sparkline && <Sparkline data={sparkline} stroke={c.stroke} />}

      {/* corner accent glow */}
      <div
        className="pointer-events-none absolute -top-10 -right-10 w-28 h-28 rounded-full blur-2xl opacity-10 transition-opacity group-hover:opacity-20"
        style={{ background: c.glow }}
      />
    </motion.div>
  );
}
