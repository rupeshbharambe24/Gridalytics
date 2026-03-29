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
  color?: "blue" | "emerald" | "amber" | "rose" | "violet";
  delay?: number;
}

const colorMap = {
  blue: "from-blue-500/10 to-blue-600/5 border-blue-500/20 text-blue-400",
  emerald: "from-emerald-500/10 to-emerald-600/5 border-emerald-500/20 text-emerald-400",
  amber: "from-amber-500/10 to-amber-600/5 border-amber-500/20 text-amber-400",
  rose: "from-rose-500/10 to-rose-600/5 border-rose-500/20 text-rose-400",
  violet: "from-violet-500/10 to-violet-600/5 border-violet-500/20 text-violet-400",
};

const iconBg = {
  blue: "bg-blue-500/15 text-blue-400",
  emerald: "bg-emerald-500/15 text-emerald-400",
  amber: "bg-amber-500/15 text-amber-400",
  rose: "bg-rose-500/15 text-rose-400",
  violet: "bg-violet-500/15 text-violet-400",
};

export function KPICard({ title, value, unit, subtitle, trend, icon: Icon, color = "blue", delay = 0 }: KPICardProps) {
  const TrendIcon = trend && trend > 0 ? TrendingUp : trend && trend < 0 ? TrendingDown : Minus;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay }}
      className={cn(
        "relative overflow-hidden rounded-xl border bg-gradient-to-br p-5",
        colorMap[color]
      )}
    >
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
          <div className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold text-foreground font-mono tabular-nums">
              {value ?? "---"}
            </span>
            {unit && <span className="text-sm text-muted-foreground">{unit}</span>}
          </div>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <div className={cn("p-2.5 rounded-lg", iconBg[color])}>
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

      {/* Decorative glow */}
      <div className="absolute -top-12 -right-12 w-32 h-32 rounded-full bg-current opacity-[0.03] blur-2xl" />
    </motion.div>
  );
}
