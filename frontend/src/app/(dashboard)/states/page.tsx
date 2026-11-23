"use client";

import { useState, useMemo } from "react";
import { motion } from "framer-motion";
import {
  AreaChart, Area, BarChart, Bar, ComposedChart, Line, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  Database, Cpu, Layers, CheckCircle2, CircleDashed, Activity, MapPin, Search,
} from "lucide-react";
import { useFetch } from "@/lib/hooks";
import { getStates, getStateDemand, getStateDetail, getStateForecast, StateInfo, StateForecast } from "@/lib/api";
import { ModelCard } from "@/components/dashboard/model-card";
import { PageHeader } from "@/components/layout/page-header";
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
      <div className="w-9 h-9 rounded-lg bg-brand/10 flex items-center justify-center shrink-0">
        <Icon className="w-5 h-5 text-brand" />
      </div>
      <div className="min-w-0">
        <div className="text-2xl font-semibold tabular-nums leading-none">{value}</div>
        <div className="text-xs text-muted-foreground mt-1">{label}</div>
        {sub && <div className="text-[11px] text-muted-foreground/70 mt-0.5">{sub}</div>}
      </div>
    </div>
  );
}

// Small labelled heading used above each block inside the detail panel.
function SectionLabel({ children }: { children: React.ReactNode }) {
  return <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{children}</div>;
}

// A card shell so every block in the detail panel reads as one system.
function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("bg-card border border-border rounded-xl p-5", className)}>{children}</div>;
}

export default function StatesPage() {
  const { data, loading } = useFetch(getStates, []);
  const [sel, setSel] = useState<string>("karnataka");
  const [query, setQuery] = useState("");

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

  // Full detail (all resolutions' models with metadata) for the selected state.
  const { data: detail } = useFetch(() => getStateDetail(selCode), [selCode]);
  const models =
    detail?.code === selCode && detail.models?.length
      ? detail.models
      : selected?.model
      ? [selected.model]
      : [];

  // Day-ahead forecast for the selected state (only when it has a model).
  const { data: forecast } = useFetch<StateForecast | null>(
    () => (selected?.has_model ? getStateForecast(selCode) : Promise.resolve(null)),
    [selCode, selected?.has_model],
  );
  const fcData = useMemo(() => {
    const f = forecast;
    if (!f?.predicted_mw?.length || f.state !== selCode) return null;
    const pts = f.timestamps.map((t, i) => ({
      t: fmtTime(t),
      pred: f.predicted_mw[i],
      base: f.lower_bound_mw[i],
      band: Math.max(0, f.upper_bound_mw[i] - f.lower_bound_mw[i]),
    }));
    const lo = Math.min(...f.lower_bound_mw);
    const hi = Math.max(...f.upper_bound_mw);
    const pad = (hi - lo) * 0.1 || hi * 0.05;
    const d0 = Math.max(0, Math.floor((lo - pad) / 500) * 500);
    const d1 = Math.ceil((hi + pad) / 500) * 500;
    return {
      pts,
      domain: [d0, d1] as [number, number],
      res: f.resolution,
      model: f.served_model,
      date: f.timestamps[0]?.slice(0, 10),
    };
  }, [forecast, selCode]);

  const byRegion = useMemo(() => {
    const m: Record<string, StateInfo[]> = {};
    for (const s of states) (m[s.region] ||= []).push(s);
    return m;
  }, [states]);

  // Filtered view of the master list — name/code search keeps the compact list
  // usable across all 36 states without taking any extra vertical room.
  const q = query.trim().toLowerCase();
  const filteredByRegion = useMemo(() => {
    if (!q) return byRegion;
    const m: Record<string, StateInfo[]> = {};
    for (const r of REGION_ORDER) {
      const hit = (byRegion[r] ?? []).filter(
        (s) => s.name.toLowerCase().includes(q) || s.code.toLowerCase().includes(q),
      );
      if (hit.length) m[r] = hit;
    }
    return m;
  }, [byRegion, q]);
  const noMatches = REGION_ORDER.every((r) => !filteredByRegion[r]?.length);

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
  // Compact axis labels (e.g. 18,332 -> "18k") so Y-ticks never clip the plot.
  const kMW = (v: number) => (Math.abs(v) >= 1000 ? `${Math.round(v / 1000)}k` : `${Math.round(v)}`);

  const tooltipStyle = { background: "hsl(var(--card))", border: "1px solid hsl(var(--border))", borderRadius: 8, fontSize: 12 };

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="All-India rollout"
        title="State-wise Grid"
        icon={MapPin}
        subtitle="Every state's data source, scraper and collection status — scaling the Delhi pipeline nationwide, with a day-ahead forecast per trained model."
      />

      {/* summary */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <SummaryCard icon={Layers} label="States & UTs" value={summary.total ?? 36} />
        <SummaryCard icon={Database} label="Collecting data" value={summary.with_data ?? 0} sub="rows stored" />
        <SummaryCard icon={Cpu} label="Models trained" value={summary.with_model ?? 0} />
        <SummaryCard icon={CheckCircle2} label="Direct scrapers" value={summary.direct ?? 0} />
        <SummaryCard icon={Activity} label="Fallback (PSP)" value={summary.fallback ?? 0} />
        <SummaryCard icon={CircleDashed} label="Deferred" value={summary.deferred ?? 0} />
      </div>

      {/* master-detail: a compact searchable list on the left, the detail takes the room */}
      <div className="grid grid-cols-1 lg:grid-cols-[clamp(240px,22vw,296px)_1fr] gap-5 items-start">
        {/* ---- master list ---- */}
        <aside className="bg-card border border-border rounded-xl overflow-hidden lg:sticky lg:top-6">
          <div className="p-3 border-b border-border">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search states…"
                aria-label="Search states"
                className="w-full pl-8 pr-2.5 py-2 text-sm rounded-lg bg-muted/40 border border-border focus:outline-none focus:ring-2 focus:ring-brand/40 placeholder:text-muted-foreground"
              />
            </div>
          </div>
          <div className="max-h-[52vh] lg:max-h-[calc(100vh-14rem)] overflow-y-auto p-2 space-y-3">
            {loading && <div className="text-sm text-muted-foreground px-2 py-1">Loading states…</div>}
            {REGION_ORDER.filter((r) => filteredByRegion[r]?.length).map((region) => (
              <div key={region}>
                <div className="px-2 mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                  {region}
                </div>
                <div className="space-y-0.5">
                  {filteredByRegion[region].map((s) => (
                    <button
                      key={s.code}
                      onClick={() => setSel(s.code)}
                      aria-pressed={selCode === s.code}
                      aria-label={`${s.name}${s.discom_level ? ", DISCOM-level" : ""}${s.has_model ? ", model trained" : s.has_data ? ", collecting data" : ""}`}
                      className={cn(
                        "w-full flex items-center gap-2 pl-2.5 pr-2 py-1.5 rounded-lg text-left text-[13px] transition-colors",
                        selCode === s.code
                          ? "bg-brand/10 text-foreground font-medium"
                          : "text-muted-foreground hover:bg-accent hover:text-foreground",
                      )}
                    >
                      <span
                        className={cn(
                          "w-1.5 h-1.5 rounded-full shrink-0",
                          s.tier === "direct" ? "bg-emerald-400" : s.tier === "deferred" ? "bg-muted-foreground/30" : "bg-sky-400/50",
                        )}
                      />
                      <span className="flex-1 truncate">{s.name}</span>
                      {s.discom_level && <span className="text-brand text-[11px] shrink-0" title="DISCOM-level">◆</span>}
                      {s.has_model ? (
                        <Cpu className="w-3.5 h-3.5 text-emerald-400 shrink-0" aria-hidden="true" />
                      ) : s.has_data ? (
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400/70 shrink-0" title="collecting" />
                      ) : null}
                    </button>
                  ))}
                </div>
              </div>
            ))}
            {!loading && noMatches && (
              <div className="text-sm text-muted-foreground px-2 py-3">No states match “{query}”.</div>
            )}
          </div>
          <div className="border-t border-border p-3 flex flex-col gap-1.5 text-[11px] text-muted-foreground">
            <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Direct scraper</span>
            <span className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-sky-400/50" /> National (PSP) fallback</span>
            <span className="flex items-center gap-2"><Cpu className="w-3 h-3 text-emerald-400" /> model trained · <span className="text-brand">◆</span> DISCOM-level</span>
          </div>
        </aside>

        {/* ---- detail ---- */}
        <div className="min-w-0">
          {!selected ? (
            <Panel className="p-10 text-center text-sm text-muted-foreground">
              Select a state to see its data source, models and forecast.
            </Panel>
          ) : (
            <motion.div
              key={selCode}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3 }}
              className="space-y-5"
            >
              {/* header */}
              <Panel>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div>
                    <div className="flex items-center gap-2 flex-wrap">
                      <h2 className="text-2xl font-semibold tracking-tight">{selected.name}</h2>
                      <span className={cn("text-[10px] font-mono px-2 py-0.5 rounded-full border", TIER_BADGE[selected.tier])}>
                        {TIER_LABEL[selected.tier]}
                      </span>
                      {selected.discom_level && (
                        <span className="text-[10px] text-brand border border-brand/40 bg-brand/10 rounded-full px-2 py-0.5">DISCOM-level</span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground font-mono mt-1">{selected.region} regional grid</div>
                  </div>
                  <div className="flex items-center gap-2 flex-wrap justify-end">
                    <div className="rounded-lg bg-muted/40 border border-border px-3 py-1.5 text-right">
                      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Rows stored</div>
                      <div className="text-base font-semibold tabular-nums leading-tight">{selected.rows_stored.toLocaleString("en-IN")}</div>
                    </div>
                    {demand?.latest && (
                      <div className="rounded-lg bg-muted/40 border border-border px-3 py-1.5 text-right">
                        <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Latest reading</div>
                        <div className="text-base font-semibold tabular-nums leading-tight">{fmtTime(demand.latest)}</div>
                      </div>
                    )}
                  </div>
                </div>
              </Panel>

              <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
                {/* ---- main column: forecast + demand charts ---- */}
                <div className="xl:col-span-2 space-y-5 min-w-0">
                  {/* forecast — the headline block, now with real room */}
                  <Panel>
                    <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
                      <SectionLabel>Day-ahead forecast{fcData?.date ? ` · ${fcData.date}` : ""}</SectionLabel>
                      {fcData && <span className="text-[10px] text-muted-foreground font-mono">{fcData.model} · {fcData.res}</span>}
                    </div>
                    {fcData ? (
                      fcData.pts.length > 1 ? (
                        <div className="h-64">
                          <ResponsiveContainer width="100%" height="100%">
                            <ComposedChart data={fcData.pts} margin={{ top: 4, right: 8, left: 4, bottom: 0 }}>
                              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border" vertical={false} />
                              <XAxis dataKey="t" tick={{ fontSize: 10 }} interval="preserveStartEnd" minTickGap={48} stroke="currentColor" className="text-muted-foreground" />
                              <YAxis tick={{ fontSize: 10 }} width={46} tickFormatter={kMW} stroke="currentColor" className="text-muted-foreground" domain={fcData.domain} />
                              <Tooltip
                                contentStyle={tooltipStyle}
                                formatter={(v: any, n: any) => [`${Number(v).toLocaleString("en-IN")} MW`, n === "pred" ? "forecast" : n]}
                              />
                              <Area stackId="ci" dataKey="base" stroke="none" fill="transparent" isAnimationActive={false} />
                              <Area stackId="ci" dataKey="band" stroke="none" fill="hsl(var(--chart-forecast))" fillOpacity={0.15} isAnimationActive={false} />
                              <Line type="monotone" dataKey="pred" stroke="hsl(var(--chart-forecast))" strokeWidth={2} dot={false} />
                            </ComposedChart>
                          </ResponsiveContainer>
                        </div>
                      ) : (
                        <div className="bg-brand/10 border border-brand/30 rounded-lg p-5 flex items-baseline gap-3 flex-wrap">
                          <span className="text-3xl font-semibold tabular-nums text-brand">{Math.round(fcData.pts[0].pred).toLocaleString("en-IN")}</span>
                          <span className="text-sm text-muted-foreground">MW predicted peak</span>
                          <span className="text-[11px] text-muted-foreground ml-auto">
                            90% interval: {Math.round(fcData.pts[0].base).toLocaleString("en-IN")}–{Math.round(fcData.pts[0].base + fcData.pts[0].band).toLocaleString("en-IN")} MW
                          </span>
                        </div>
                      )
                    ) : (
                      <div className="h-64 flex items-center justify-center text-center text-sm text-muted-foreground bg-muted/20 border border-border rounded-lg">
                        No day-ahead forecast — this grid has no served model yet.
                      </div>
                    )}
                  </Panel>

                  {/* recent demand + load profile side by side */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                    <Panel>
                      <div className="flex items-center justify-between mb-2">
                        <SectionLabel>Recent demand</SectionLabel>
                        {demand?.latest && <span className="text-[10px] text-muted-foreground font-mono">→ {fmtTime(demand.latest)}</span>}
                      </div>
                      <div className="h-40">
                        {demandLoading ? (
                          <div className="h-full flex items-center justify-center text-xs text-muted-foreground">Loading…</div>
                        ) : chartData.length ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <AreaChart data={chartData} margin={{ top: 4, right: 6, left: 4, bottom: 0 }}>
                              <defs>
                                <linearGradient id="demandFill" x1="0" y1="0" x2="0" y2="1">
                                  <stop offset="0%" stopColor="hsl(var(--chart-demand))" stopOpacity={0.4} />
                                  <stop offset="100%" stopColor="hsl(var(--chart-demand))" stopOpacity={0} />
                                </linearGradient>
                              </defs>
                              <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-border" vertical={false} />
                              <XAxis dataKey="t" tick={{ fontSize: 9 }} interval="preserveStartEnd" minTickGap={40} stroke="currentColor" className="text-muted-foreground" />
                              <YAxis tick={{ fontSize: 9 }} width={40} tickFormatter={kMW} stroke="currentColor" className="text-muted-foreground" domain={["auto", "auto"]} />
                              <Tooltip
                                contentStyle={tooltipStyle}
                                formatter={(v: any) => [`${Number(v).toLocaleString("en-IN")} MW`, "demand"]}
                              />
                              <Area type="monotone" dataKey="mw" stroke="hsl(var(--chart-demand))" strokeWidth={1.5} fill="url(#demandFill)" />
                            </AreaChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No demand series stored yet.</div>
                        )}
                      </div>
                    </Panel>

                    <Panel>
                      <SectionLabel>Load profile — avg by hour</SectionLabel>
                      <div className="h-40 mt-2">
                        {analysis ? (
                          <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={analysis.hourly} margin={{ top: 4, right: 4, left: 4, bottom: 0 }}>
                              <XAxis dataKey="h" tick={{ fontSize: 9 }} interval={2} stroke="currentColor" className="text-muted-foreground" />
                              <YAxis tick={{ fontSize: 9 }} width={40} tickFormatter={kMW} stroke="currentColor" className="text-muted-foreground" domain={["auto", "auto"]} />
                              <Tooltip
                                contentStyle={tooltipStyle}
                                formatter={(v: any) => [`${Number(v).toLocaleString("en-IN")} MW`, "avg"]}
                                labelFormatter={(l) => `${l}:00`}
                              />
                              <Bar dataKey="mw" fill="hsl(var(--chart-demand))" radius={[2, 2, 0, 0]} />
                            </BarChart>
                          </ResponsiveContainer>
                        ) : (
                          <div className="h-full flex items-center justify-center text-xs text-muted-foreground">No series yet.</div>
                        )}
                      </div>
                    </Panel>
                  </div>
                </div>

                {/* ---- side column: stats, source, models ---- */}
                <div className="space-y-5 min-w-0">
                  <Panel>
                    <SectionLabel>Last 14 days</SectionLabel>
                    {analysis ? (
                      <div className="grid grid-cols-3 gap-2 mt-3">
                        {([["Peak", `${fmtMW(analysis.peak)}`], ["Average", `${fmtMW(analysis.avg)}`], ["Load factor", `${analysis.loadFactor.toFixed(0)}%`]] as const).map(([l, v]) => (
                          <div key={l} className="bg-muted/30 border border-border rounded-lg p-2.5">
                            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{l}</div>
                            <div className="text-base font-semibold tabular-nums leading-tight mt-0.5">{v}</div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-xs text-muted-foreground mt-3">No demand series stored for this grid yet.</div>
                    )}
                  </Panel>

                  <Panel>
                    <SectionLabel>Data source</SectionLabel>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-2 text-sm mt-3">
                      <dt className="text-muted-foreground">Method</dt><dd className="font-mono text-xs self-center">{selected.method}</dd>
                      <dt className="text-muted-foreground">Scraper</dt><dd className="font-mono text-xs self-center break-all">{selected.scraper ?? "—"}</dd>
                      <dt className="text-muted-foreground">DISCOMs</dt><dd className="text-xs self-center">{selected.discoms.length ? selected.discoms.join(" · ") : "single utility"}</dd>
                    </dl>
                  </Panel>

                  <Panel>
                    <SectionLabel>{models.length > 1 ? `${models.length} models trained` : "Model"}</SectionLabel>
                    <div className="space-y-2 mt-3">
                      {models.length ? (
                        models.map((mdl, i) => <ModelCard key={mdl.resolution} m={mdl} delay={i * 0.05} />)
                      ) : selected.has_data ? (
                        <div className="text-xs text-muted-foreground bg-muted/30 border border-border rounded-lg p-3">
                          Collecting data — no model trained yet. Run <span className="font-mono">train_state.py {selected.code}</span>.
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground bg-muted/30 border border-border rounded-lg p-3">
                          No data collected yet{selected.tier === "deferred" ? " (source access-gated)." : selected.tier === "fallback" ? " — covered by the Grid-India PSP fallback once it runs." : "."}
                        </div>
                      )}
                    </div>
                  </Panel>
                </div>
              </div>
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
