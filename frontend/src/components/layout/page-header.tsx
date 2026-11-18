"use client";

import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  subtitle?: React.ReactNode;
  icon?: LucideIcon;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHeader({ eyebrow, title, subtitle, icon: Icon, actions, className }: PageHeaderProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
      className={cn("flex items-start justify-between gap-4 flex-wrap", className)}
    >
      <div className="min-w-0">
        {eyebrow && (
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-brand mb-1.5">{eyebrow}</p>
        )}
        <div className="flex items-center gap-2.5">
          {Icon && (
            <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-brand/12 text-brand shrink-0">
              <Icon className="w-[18px] h-[18px]" />
            </span>
          )}
          <h1 className="text-2xl font-bold tracking-tight text-foreground text-balance">{title}</h1>
        </div>
        {subtitle && <p className="text-sm text-muted-foreground mt-1.5 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </motion.div>
  );
}
