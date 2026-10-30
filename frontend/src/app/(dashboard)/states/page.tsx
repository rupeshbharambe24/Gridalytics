"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Database, Cpu, Layers, CheckCircle2, CircleDashed, Activity, MapPin,
} from "lucide-react";
import { useFetch } from "@/lib/hooks";
import { getStates, getStateDemand, StateInfo } from "@/lib/api";
import { cn } from "@/lib/utils";

const REGION_ORDER = ["Northern", "Western", "Southern", "Eastern", "North-Eastern"];

const TIER_BADGE: Record<string, string> = {
  direct: "bg-emerald-500/15 text-emerald-400 border-emerald-500/40",
  fallback: "bg-muted/60 text-muted-foreground border-border",
  deferred: "bg-amber-500/10 text-amber-400 border-amber-500/40 border-dashed",
};
const TIER_LABEL: Record<string, string> = {
  direct: "Direct scraper",
  fallback: "National fallback",
  deferred: "Deferred",
};

function fmtTime(t: string) {
  // "2026-10-27 14:00:00" -> "27 Oct 14:00"
  const d = new Date(t.replace(" ", "T"));
  if (isNaN(d.getTime())) return t;
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function SummaryCard({ icon: Icon, label, value, sub }: { icon: any; label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-card border border-border rounded-xl p-4 flex items-start gap-3 min-w-0">
      <div className="w-9 h-9 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0">
        <Icon className="w-5 h-5 text-blue-400" />
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold tabular-nums leading-none">{value}</div>
        <div className="text-xs text-muted-foreground mt-1">{label}</div>
        {sub && <div className="text-[11px] text-muted-foreground/70 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

export default function StatesPage() {
  const { data, loading } = useFetch(getStates, []);
  const [sel, setSel] = useState<string>("karnataka");

  const states = data?.states ?? [];
  const summary = data?.summary ?? {};
  const selected: StateInfo | undefined = useMemo(
    () => states.find((s) => s.code === sel) ?? states.find((s) => s.has_data),
    [states, sel]
  );
  const selCode = selected?.code ?? sel;

  const { data: demand, loading: demandLoading } = useFetch(
    () => getStateDemand(selCode, 14),
    [selCode],
  );

  const byRegion = useMemo(() => {
    const m: Record<string, StateInfo[]> = {};
    for (const s of states) (m[s.region] ||= []).push(s);
    return m;
  }, [states]);

  // All analysis is computed client-side from the (already-capped) series — no
  // extra network weight, memoized so switching states stays instant.
  const analysis = useMemo(() => {
    const s = demand?.series ?? [];
    if (!s.length) return null;
    const mws = s.map((p) => p.mw);
    let peak = -Infinity, min = Infinity, total = 0;
    for (const v of mws) { if (v > peak) peak = v; if (v < min) min = v; total += v; }
    const avg = total / mws.length;
    const sum = new Array(24).fill(0), cnt = new Array(24).fill(0);
    for (const p of s) {
      const d = new Date(p.t.replace(" ", "T"));
      if (!isNaN(d.getTime())) { const h = d.getHours(); sum[h] += p.mw; cnt[h] += 1; }
    }
    const hourly = sum.map((v, h) => ({ h: `${h}`, mw: cnt[h] ? Math.round(v / cnt[h]) : 0 }));
    const stride = Math.max(1, Math.ceil(s.length / 360));
    const area = s.filter((_, i) => i % stride === 0).map((p) => ({ t: fmtTime(p.t), mw: p.mw }));
    return { peak, min, avg, loadFactor: peak > 0 ? (avg / peak) * 100 : 0, hourly, area };
  }, [demand]);
  const chartData = analysis?.area ?? [];
  const fmtMW = (v: number) => `${Math.round(v).toLocaleString("en-IN")}`;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <MapPin className="w-6 h-6 text-blue-400" /> State-wise Grid
        </h1>
        <p className="text-sm text-muted-foreground mt-1">
          The all-India rollout. Every state&apos;s data source, scraper and collection status — scaling the Delhi pipeline nationwide.
        </p>
      </div>

      {/* summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <SummaryCard icon={Layers} label="States & UTs" value={summary.total ?? 36} />
        <SummaryCard icon={Database} label="Collecting data" value={summary.with_data ?? 0} sub="rows stored" />
        <SummaryCard icon={Cpu} label="Models trained" value={summary.with_model ?? 0} />
        <SummaryCard icon={CheckCircle2} label="Direct scrapers" value={summary.direct ?? 0} />
        <SummaryCard icon={Activity} label="Fallback (PSP)" value={summary.fallback ?? 0} />
        <SummaryCard icon={CircleDashed} label="Deferred" value={summary.deferred ?? 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_360px] gap-6 items-start">
        {/* map / state list */}
        <div className="space-y-5">
          {loading && <div className="text-sm text-muted-foreground">Loading states…</div>}
          {REGION_ORDER.filter((r) => byRegion[r]?.length).map((region) => (
            <div key={region}>
              <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-2">
                {region} grid
              </h3>
              <div className="flex flex-wrap gap-2">
                {byRegion[region].map((s) => (
                  <motion.button
                    key={s.code}
                    whileHover={{ y: -1 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => setSel(s.code)}
                    className={cn(
                      "px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors flex items-center gap-1.5",
                      s.tier === "direct"
                        ? "bg-emerald-500/10 border-emerald-500/40 text-foreground"
                        : s.tier === "deferred"
                        ? "border-dashed border-border text-muted-foreground"
                        : "bg-card border-border text-foreground",
                      selCode === s.code && "ring-2 ring-blue-500",
                    )}
                  >
                    {s.name}
                    {s.discom_level && <span className="text-blue-400" title="DISCOM-level">◆</span>}
                    {s.has_model && <Cpu className="w-3 h-3 text-emerald-400" aria-label="model trained" />}
                    {s.has_data && !s.has_model && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" title="collecting" />}
                  </motion.button>
                ))}
              </div>
            </div>
          ))}
          <div className="flex flex-wrap gap-4 text-[11px] text-muted-foreground pt-1">
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-emerald-500/40 border border-emerald-500/40" /> Direct scraper</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded bg-card border border-border" /> National fallback</span>
            <span className="flex items-center gap-1.5"><span className="w-3 h-3 rounded border border-dashed border-border" /> Deferred</span>
            <span className="flex items-center gap-1.5"><Cpu className="w-3 h-3 text-emerald-400" /> model trained</span>
            <span className="flex items-center gap-1.5"><span className="text-blue-400">◆</span> DISCOM-level</span>
          </div>
        </div>

        {/* detail panel */}
        <div className="bg-card border border-border rounded-xl p-5 lg:sticky lg:top-4 space-y-4">
          {!selected ? (
            <div className="text-sm text-muted-foreground">Select a state.</div>
          ) : (
            <>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="text-lg font-semibold">{selected.name}</h2>
                  <span className={cn("text-[10px] font-mono px-2 py-0.5 rounded-full border", TIER_BADGE[selected.tier])}>
                    {TIER_LABEL[selected.tier]}
                  </span>
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-0.5">{selected.region} regional grid</div>
              </div>

              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                <dt className="text-muted-foreground">Method</dt><dd className="font-mono text-xs self-center">{selected.method}</dd>
                <dt className="text-muted-foreground">Scraper</dt><dd className="font-mono text-xs self-center break-all">{selected.scraper ?? "—"}</dd>
                <dt className="text-muted-foreground">DISCOMs</dt><dd className="text-xs self-center">{selected.discoms.length ? selected.discoms.join(" · ") : "single utility"}</dd>
                <dt className="text-muted-foreground">Rows stored</dt><dd className="tabular-nums self-center">{selected.rows_stored.toLocaleString("en-IN")}</dd>
              </dl>

              {/* model metrics */}
              {selected.model ? (
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3">
                    <div className="text-[10px] uppercase tracking-wide text-emerald-400/90">Champion MAPE</div>
                    <div className="text-xl font-semibold tabular-nums">
                      {selected.model.champion_cv_mape != null ? `${selected.model.champion_cv_mape}%` : "—"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">{selected.model.champion ?? selected.model.served_model ?? "model"} · {selected.model.resolution}</div>
                  </div>
                  <div className="bg-muted/40 border border-border rounded-lg p-3">
                    <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Persistence</div>
                    <div className="text-xl font-semibold tabular-nums">
                      {selected.model.persistence_mape != null ? `${selected.model.persistence_mape}%` : "—"}
                    </div>
                    <div className="text-[10px] text-muted-foreground">baseline to beat</div>
                  </div>
                </div>
              ) : selected.has_data ? (
                <div className="text-xs text-muted-foreground bg-muted/30 border border-border rounded-lg p-3">
                  Collecting data — no model trained yet. Run <span className="font-mono">train_state.py {selected.code}</span>.
                </div>
              ) : (
                <div className="text-xs text-muted-foreground bg-muted/30 border border-border rounded-lg p-3">
                  No data collected yet{selected.tier === "deferred" ? " (source access-gated)." : selected.tier === "fallback" ? " — covered by the Grid-India PSP fallback once it runs." : "."}
                </div>
              )}

              {/* analysis (client-side from the series) */}
              {analysis && (
                <>
                  <div className="grid grid-cols-3 gap-2">
                    {([["Peak", `${fmtMW(analysis.peak)} MW`], ["Average", `${fmtMW(analysis.avg)} MW`], ["Load factor", `${analysis.loadFactor.toFixed(0)}%`]] as const).map(([l, v]) => (
                      <div key={l} className="bg-muted/30 border border-border rounded-lg p-2.5">
                        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div>
                        <div className="text-base font-semibold tabular-nums leading-tight mt-0.5">{v}</div>
                      </div>
                    ))}
                  </div>
                  <div>
                    <span className="text-xs font-medium text-muted-foreground">Daily load profile — avg by hour</span>
                    <div className="h-28 mt-1.5">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart data={analysis.hourly} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                          <XAxis dataKey="h" tick={{ fontSize: 8 }} interval={2} stroke="currentColor" className="text-muted-foreground" />
                          <YAxis tick={{ fontSize: 8 }} width={42} stroke="currentColor" className="text-muted-foreground" domain={["auto", "auto"]} />
                          <Tooltip
                            contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                            formatter={(v: any) => [`${Number(v).toLocaleString("en-IN")} MW`, "avg"]}
                            labelFormatter={(l) => `${l}:00`}
                          />
                          <Bar dataKey="mw" fill="#3b82f6" radius={[2, 2, 0, 0]} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </>
              )}

              {/* demand chart */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs font-medium text-muted-foreground">Recent demand</span>
                  {demand?.latest && <span className="text-[10px] text-muted-foreground font-mono">→ {fmtTime(demand.latest)}</span>}
                </div>
                <div className="h-40">
                  {demandLoading ? (
                    <div className="h-full flex items-center justify-center text-xs text-muted-foreground">Loading…</div>
                  ) : chartData.length ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 4, right: 6, left: -18, bottom: 0 }}>
                        <defs>
                          <linearGradient id="demandFill" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#3b82f6" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border" vertical={false} />
                        <XAxis dataKey="t" tick={{ fontSize: 9 }} interval="preserveStartEnd" minTickGap={40} stroke="currentColor" className="text-muted-foreground" />
                        <YAxis tick={{ fontSize: 9 }} width={44} stroke="currentColor" className="text-muted-foreground" domain={["auto", "auto"]} />
                        <Tooltip
                          contentStyle={{ background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 }}
                          formatter={(v: any) => [`${Number(v).toLocaleString("en-IN")} MW`, "demand"]}
                        />
                        <Area type="monotone" dataKey="mw" stroke="#3b82f6" strokeWidth={1.5} fill="url(#demandFill)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No demand series stored yet.</div>
                  )}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
