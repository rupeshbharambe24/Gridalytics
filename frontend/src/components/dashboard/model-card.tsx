"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Trophy, CheckCircle2, XCircle, Calendar, Database, Layers, Clock,
  ChevronDown, ChevronRight, Cpu,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { StateModelInfo } from "@/lib/api";

const RES_LABEL: Record<string, string> = {
  "5min": "5-minute", "15min": "15-minute", hourly: "Hourly",
  daily: "Daily peak", multi: "Multi-resolution",
};

const fmtInt = (n?: number) => (n == null ? "—" : Math.round(n).toLocaleString("en-IN"));
const fmtDate = (s?: string) => {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d.getTime()) ? s : d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
};

export function ModelCard({ m, delay = 0 }: { m: StateModelInfo; delay?: number }) {
  const [showFeats, setShowFeats] = useState(false);
  const beats = m.beats_persistence;
  const champMape = m.champion_cv_mape;
  const persMape = m.persistence_mape;
  const impr = m.improvement_pts ?? (champMape != null && persMape != null ? persMape - champMape : undefined);

  // Delhi-style note model (no per-resolution metrics stored here)
  if (m.note && champMape == null) {
    return (
      <div className="rounded-xl border border-border bg-card p-4">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-blue-400" />
          <span className="font-semibold">{RES_LABEL[m.resolution] ?? m.resolution}</span>
          {m.served_model && <span className="text-xs font-mono text-muted-foreground">{m.served_model}</span>}
        </div>
        <p className="text-xs text-muted-foreground mt-2">{m.note}</p>
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay }}
      className="rounded-xl border border-border bg-card overflow-hidden"
    >
      {/* header */}
      <div className="flex items-center justify-between gap-2 px-4 pt-4">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold">{RES_LABEL[m.resolution] ?? m.resolution}</span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/60 text-muted-foreground shrink-0">
            {m.source === "psp" ? "PSP" : m.source === "state_demand" ? "SLDC" : (m.source ?? "SLDC")}
          </span>
        </div>
        {beats != null && (
          <span className={cn(
            "text-[10px] font-medium px-2 py-0.5 rounded-full border flex items-center gap-1 shrink-0",
            beats ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/40"
                  : "bg-amber-500/10 text-amber-400 border-amber-500/40",
          )}>
            {beats ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
            {beats ? "beats persistence" : "below persistence"}
          </span>
        )}
      </div>

      {/* hero metric */}
      <div className="px-4 py-3 flex items-end gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-wide text-muted-foreground flex items-center gap-1">
            <Trophy className="w-3 h-3 text-amber-400" /> {m.champion ?? m.served_model ?? "champion"} MAPE
          </div>
          <div className="text-3xl font-bold tabular-nums leading-none mt-1">
            {champMape != null ? `${champMape}%` : "—"}
          </div>
        </div>
        {impr != null && (
          <div className={cn("text-xs font-medium mb-1", impr >= 0 ? "text-emerald-400" : "text-amber-400")}>
            {impr >= 0 ? "−" : "+"}{Math.abs(impr).toFixed(2)} pts vs naive
          </div>
        )}
      </div>

      {/* metric grid */}
      <div className="grid grid-cols-3 gap-px bg-border">
        {([
          ["Persistence", persMape != null ? `${persMape}%` : "—"],
          ["R²", m.champion_cv_r2 != null ? m.champion_cv_r2.toFixed(3) : "—"],
          ["RMSE", m.champion_cv_rmse != null ? fmtInt(m.champion_cv_rmse) : "—"],
        ] as const).map(([l, v]) => (
          <div key={l} className="bg-card px-3 py-2">
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div>
            <div className="text-sm font-semibold tabular-nums">{v}</div>
          </div>
        ))}
      </div>

      {/* details */}
      <dl className="px-4 py-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs">
        <dt className="text-muted-foreground flex items-center gap-1"><Calendar className="w-3 h-3" /> Trained on</dt>
        <dd className="self-center">{fmtDate(m.data_period_start)} → {fmtDate(m.data_period_end)}</dd>

        <dt className="text-muted-foreground flex items-center gap-1"><Database className="w-3 h-3" /> Data size</dt>
        <dd className="self-center tabular-nums">
          {fmtInt(m.data_rows_usable)} usable
          {m.data_rows_raw != null && <span className="text-muted-foreground"> / {fmtInt(m.data_rows_raw)} raw</span>}
          {m.data_mean_mw != null && <span className="text-muted-foreground"> · ~{fmtInt(m.data_mean_mw)} MW avg</span>}
        </dd>

        {m.db_source?.length ? (
          <>
            <dt className="text-muted-foreground">Provenance</dt>
            <dd className="self-center font-mono text-[11px] break-all">{m.db_source.join(", ")}</dd>
          </>
        ) : null}

        <dt className="text-muted-foreground flex items-center gap-1"><Layers className="w-3 h-3" /> Features</dt>
        <dd className="self-center">
          {m.features ?? m.feature_list?.length ?? "—"}
          {m.weather != null && <span className="text-muted-foreground"> · {m.weather ? "with weather" : "no weather"}</span>}
        </dd>

        <dt className="text-muted-foreground">Validation</dt>
        <dd className="self-center">
          {m.cv_folds ? `${m.cv_folds}-fold walk-forward CV` : "walk-forward CV"}
          {m.holdout_rows != null && <span className="text-muted-foreground"> · {fmtInt(m.holdout_rows)}-row holdout</span>}
        </dd>

        {m.models_cv_mape && Object.keys(m.models_cv_mape).length > 1 ? (
          <>
            <dt className="text-muted-foreground">Candidates</dt>
            <dd className="self-center font-mono text-[11px]">
              {Object.entries(m.models_cv_mape).sort((a, b) => a[1] - b[1]).map(([k, v]) => `${k} ${v}%`).join(" · ")}
            </dd>
          </>
        ) : null}

        {m.trained_at ? (
          <>
            <dt className="text-muted-foreground flex items-center gap-1"><Clock className="w-3 h-3" /> Last trained</dt>
            <dd className="self-center text-muted-foreground">{fmtDate(m.trained_at)}</dd>
          </>
        ) : null}
      </dl>

      {/* served != champion (save fell back) */}
      {m.served_model && m.champion && m.served_model !== m.champion && (
        <div className="px-4 pb-2 -mt-1 text-[11px] text-amber-400/90">
          Serving {m.served_model} (champion {m.champion} tied; save fell back).
        </div>
      )}

      {/* collapsible feature list */}
      {m.feature_list?.length ? (
        <div className="border-t border-border">
          <button
            onClick={() => setShowFeats((v) => !v)}
            className="w-full px-4 py-2 flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {showFeats ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
            {m.feature_list.length} features
          </button>
          {showFeats && (
            <div className="px-4 pb-3 flex flex-wrap gap-1">
              {m.feature_list.map((f) => (
                <span key={f} className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-muted/50 text-muted-foreground">{f}</span>
              ))}
            </div>
          )}
        </div>
      ) : null}
    </motion.div>
  );
}
