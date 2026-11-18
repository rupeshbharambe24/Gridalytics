"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  FlaskConical, Loader2, Thermometer, Droplets, Calendar,
  Cloud, AlertTriangle, PartyPopper, Info, Save, X, TrendingUp, TrendingDown,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { DemandChart } from "@/components/charts/demand-chart";
import { PageHeader } from "@/components/layout/page-header";
import { getForecast, getWhatIf } from "@/lib/api";

export default function WhatIfPage() {
  const [date, setDate] = useState(new Date().toISOString().split("T")[0]);
  const [resolution, setResolution] = useState<"5min" | "hourly" | "daily">("hourly");
  const [temp, setTemp] = useState(35);
  const [humidity, setHumidity] = useState(50);
  const [aqi, setAqi] = useState(100);
  const [cloudCover, setCloudCover] = useState(50);
  const [isHoliday, setIsHoliday] = useState(false);
  const [festival, setFestival] = useState("none");
  const [loading, setLoading] = useState(false);
  const [baseline, setBaseline] = useState<any>(null);
  const [scenario, setScenario] = useState<any>(null);
  const [savedScenarios, setSavedScenarios] = useState<any[]>([]);

  // Load saved scenarios from localStorage on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem("gridalytics_scenarios");
      if (saved) setSavedScenarios(JSON.parse(saved));
    } catch {}
  }, []);

  const saveScenario = () => {
    if (!scenario) return;
    const entry = {
      id: Date.now(),
      date, resolution, temp, humidity, aqi, cloudCover, isHoliday, festival,
      avgMW: Math.round(scenAvg),
      peakMW: Math.round(scenPeak),
      diffPct: Number(diffPct.toFixed(1)),
    };
    const updated = [entry, ...savedScenarios].slice(0, 10);
    setSavedScenarios(updated);
    try { localStorage.setItem("gridalytics_scenarios", JSON.stringify(updated)); } catch {}
    import("sonner").then(({ toast }) => toast.success("Scenario saved"));
  };

  const deleteScenario = (id: number) => {
    const updated = savedScenarios.filter((s) => s.id !== id);
    setSavedScenarios(updated);
    try { localStorage.setItem("gridalytics_scenarios", JSON.stringify(updated)); } catch {}
  };

  const loadScenario = (s: any) => {
    setDate(s.date); setResolution(s.resolution); setTemp(s.temp);
    setHumidity(s.humidity); setAqi(s.aqi); setCloudCover(s.cloudCover);
    setIsHoliday(s.isHoliday); setFestival(s.festival);
  };

  const runScenario = async () => {
    setLoading(true);
    try {
      const overrides: Record<string, any> = {
        temperature: temp,
        humidity,
        is_holiday: isHoliday || festival !== "none",
        aqi,
      };
      const [base, whatif] = await Promise.all([
        getForecast(resolution, date),
        getWhatIf({ date, resolution, overrides }),
      ]);
      setBaseline(base);
      setScenario(whatif);
    } catch (e) {
      console.error(e);
      import("sonner").then(({ toast }) => toast.error("Could not run scenario — check the backend is running."));
    } finally {
      setLoading(false);
    }
  };

  const chartData = baseline
    ? baseline.timestamps.map((t: string, i: number) => ({
        time: new Date(t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
        demand: baseline.predicted_mw[i],
      }))
    : [];

  const forecastData = scenario
    ? scenario.timestamps.map((t: string, i: number) => ({
        time: new Date(t).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }),
        predicted: scenario.predicted_mw[i],
        lower: scenario.lower_bound_mw[i],
        upper: scenario.upper_bound_mw[i],
      }))
    : [];

  const baseAvg = baseline ? baseline.predicted_mw.reduce((a: number, b: number) => a + b, 0) / baseline.predicted_mw.length : 0;
  const scenAvg = scenario ? scenario.predicted_mw.reduce((a: number, b: number) => a + b, 0) / scenario.predicted_mw.length : 0;
  const basePeak = baseline ? Math.max(...baseline.predicted_mw) : 0;
  const scenPeak = scenario ? Math.max(...scenario.predicted_mw) : 0;
  const diffPct = baseAvg > 0 ? ((scenAvg - baseAvg) / baseAvg) * 100 : 0;
  const peakDiffPct = basePeak > 0 ? ((scenPeak - basePeak) / basePeak) * 100 : 0;

  const sliderCls = "w-full h-2 bg-accent rounded-full appearance-none cursor-pointer";

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Scenario lab"
        title="What-If Scenarios"
        subtitle="Override weather, pollution, and events to see how Delhi's demand responds — counterfactually, against the model's own baseline."
        icon={FlaskConical}
      />

      {/* Explanation */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-xl border border-brand/20 bg-brand/5 p-4">
        <div className="flex items-start gap-3">
          <Info className="w-5 h-5 text-brand shrink-0 mt-0.5" />
          <div className="text-sm text-muted-foreground space-y-1">
            <p className="text-foreground font-medium">How what-if scenarios work</p>
            <p>
              The <strong className="text-foreground">baseline</strong> (green line) uses the day&apos;s actual/predicted
              conditions. The <strong className="text-foreground">scenario</strong> (blue dashed) re-runs the model with your
              overrides. The difference is the estimated MW impact.
            </p>
            <p className="text-xs">
              Try: a 45&#176;C heatwave, an AQI 400 pollution event, a Diwali holiday, or monsoon (high humidity + cloud cover).
            </p>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Controls */}
        <motion.div initial={{ opacity: 0, x: -16 }} animate={{ opacity: 1, x: 0 }}
          className="rounded-xl border border-border bg-card shadow-card p-6 space-y-5 h-fit lg:sticky lg:top-6">
          <h2 className="text-sm font-semibold flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-brand" /> Parameters
          </h2>

          {/* Resolution */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Resolution</label>
            <div className="flex rounded-lg border border-border overflow-hidden p-0.5 gap-0.5 bg-accent/40">
              {(["5min", "hourly", "daily"] as const).map((r) => (
                <button key={r} onClick={() => setResolution(r)}
                  className={`flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${resolution === r ? "bg-brand text-brand-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}>
                  {r === "5min" ? "5-Min" : r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Date */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Date</label>
            <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="bg-background" />
          </div>

          {/* Temperature */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Thermometer className="w-3.5 h-3.5" /> Temperature</span>
              <span className="font-mono text-foreground tabular-nums">{temp}&#176;C</span>
            </label>
            <input type="range" min={5} max={50} value={temp} onChange={(e) => setTemp(+e.target.value)}
              className={`${sliderCls} accent-amber-500`} />
            <div className="flex justify-between text-[10px] text-muted-foreground"><span>5&#176;C</span><span>50&#176;C</span></div>
          </div>

          {/* Humidity */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Droplets className="w-3.5 h-3.5" /> Humidity</span>
              <span className="font-mono text-foreground tabular-nums">{humidity}%</span>
            </label>
            <input type="range" min={10} max={100} value={humidity} onChange={(e) => setHumidity(+e.target.value)}
              className={`${sliderCls} accent-sky-500`} />
          </div>

          {/* AQI */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5" /> Air Quality (AQI)</span>
              <span className={`font-mono tabular-nums ${aqi > 300 ? "text-rose-400" : aqi > 200 ? "text-amber-400" : "text-foreground"}`}>{aqi}</span>
            </label>
            <input type="range" min={0} max={500} value={aqi} onChange={(e) => setAqi(+e.target.value)}
              className={`${sliderCls} accent-rose-500`} />
            <div className="flex justify-between text-[10px] text-muted-foreground"><span>Good</span><span>Unhealthy</span><span>Hazardous</span></div>
          </div>

          {/* Cloud Cover */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center justify-between">
              <span className="flex items-center gap-1.5"><Cloud className="w-3.5 h-3.5" /> Cloud Cover</span>
              <span className="font-mono text-foreground tabular-nums">{cloudCover}%</span>
            </label>
            <input type="range" min={0} max={100} value={cloudCover} onChange={(e) => setCloudCover(+e.target.value)}
              className={`${sliderCls} accent-slate-400`} />
          </div>

          {/* Holiday */}
          <div className="flex items-center justify-between">
            <label className="text-xs font-medium text-muted-foreground">Public Holiday</label>
            <button onClick={() => setIsHoliday(!isHoliday)} aria-pressed={isHoliday}
              className={`relative w-10 h-5 rounded-full transition-colors ${isHoliday ? "bg-brand" : "bg-accent"}`}>
              <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200 ${isHoliday ? "left-[22px]" : "left-0.5"}`} />
            </button>
          </div>

          {/* Festival */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground flex items-center gap-1.5"><PartyPopper className="w-3.5 h-3.5 text-brand" /> Festival / Event</label>
            <select value={festival} onChange={(e) => setFestival(e.target.value)}
              className="w-full h-9 px-3 rounded-lg border border-border bg-background text-sm">
              <option value="none">None</option>
              <option value="diwali">Diwali (massive lighting)</option>
              <option value="holi">Holi</option>
              <option value="eid">Eid</option>
              <option value="ipl">IPL Match (evening TV)</option>
              <option value="election">Election Day</option>
            </select>
          </div>

          <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
            onClick={runScenario} disabled={loading}
            className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-brand text-brand-foreground font-medium text-sm hover:bg-brand/90 disabled:opacity-50 transition-colors shadow-sm">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FlaskConical className="w-4 h-4" />}
            Run Scenario
          </motion.button>
        </motion.div>

        {/* Results */}
        <div className="lg:col-span-2 space-y-4">
          <AnimatePresence mode="wait">
            {scenario && baseline && (
              <motion.div key="result" initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className={`rounded-xl border p-5 shadow-card ${diffPct > 0 ? "border-amber-500/30 bg-amber-500/5" : "border-brand/30 bg-brand/5"}`}>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                      {diffPct > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />} Average Demand Impact
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <span className={`text-3xl font-bold font-mono tabular-nums ${diffPct > 0 ? "text-amber-400" : "text-brand"}`}>
                        {diffPct > 0 ? "+" : ""}{diffPct.toFixed(1)}%
                      </span>
                      <span className="text-sm text-muted-foreground">({(scenAvg - baseAvg).toFixed(0)} MW)</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">Baseline {baseAvg.toFixed(0)} → Scenario {scenAvg.toFixed(0)} MW</p>
                  </div>
                  <div className={`rounded-xl border p-5 shadow-card ${peakDiffPct > 0 ? "border-rose-500/30 bg-rose-500/5" : "border-emerald-500/30 bg-emerald-500/5"}`}>
                    <p className="text-xs text-muted-foreground flex items-center gap-1.5">
                      {peakDiffPct > 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />} Peak Demand Impact
                    </p>
                    <div className="flex items-baseline gap-2 mt-1">
                      <span className={`text-3xl font-bold font-mono tabular-nums ${peakDiffPct > 0 ? "text-rose-400" : "text-emerald-400"}`}>
                        {peakDiffPct > 0 ? "+" : ""}{peakDiffPct.toFixed(1)}%
                      </span>
                      <span className="text-sm text-muted-foreground">({(scenPeak - basePeak).toFixed(0)} MW)</span>
                    </div>
                    <p className="text-xs text-muted-foreground mt-2">Baseline {basePeak.toFixed(0)} → Scenario {scenPeak.toFixed(0)} MW</p>
                  </div>
                </div>

                <div className="rounded-lg bg-accent/40 p-3 text-xs text-muted-foreground">
                  <strong className="text-foreground">How to read:</strong> green = baseline, blue dashed = your scenario.
                  Positive % = higher demand (grid needs more capacity); negative % = lower demand (potential headroom).
                </div>

                <DemandChart data={chartData} forecast={forecastData} title="Baseline vs Scenario" height={380} />

                <motion.button
                  whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}
                  onClick={saveScenario}
                  className="flex items-center gap-2 px-4 py-2 text-xs font-medium rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
                >
                  <Save className="w-3.5 h-3.5" /> Save this scenario
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>

          {!scenario && !loading && (
            <div className="flex items-center justify-center h-[400px] rounded-xl border border-dashed border-border bg-card/40">
              <div className="text-center max-w-sm px-6">
                <FlaskConical className="w-12 h-12 text-brand/25 mx-auto mb-3" />
                <p className="text-sm text-foreground font-medium">Adjust parameters and run a scenario</p>
                <p className="text-xs text-muted-foreground mt-2">
                  Try a 45&#176;C heatwave, AQI 400 pollution, a Diwali holiday, or monsoon conditions.
                </p>
              </div>
            </div>
          )}

          {loading && !scenario && (
            <div className="flex items-center justify-center h-[400px] rounded-xl border border-border bg-card/40">
              <Loader2 className="w-6 h-6 animate-spin text-brand" />
            </div>
          )}
        </div>
      </div>

      {/* Saved Scenarios */}
      {savedScenarios.length > 0 && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
          className="rounded-xl border border-border bg-card shadow-card p-5">
          <h3 className="text-sm font-semibold text-foreground mb-3">Saved scenarios ({savedScenarios.length}/10)</h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {savedScenarios.map((s) => (
              <div key={s.id} className="rounded-lg border border-border bg-accent/20 p-3 text-xs space-y-1 group relative hover:border-brand/30 transition-colors">
                <button
                  onClick={() => deleteScenario(s.id)}
                  aria-label="Delete scenario"
                  className="absolute top-2 right-2 text-muted-foreground hover:text-rose-400 opacity-0 group-hover:opacity-100 transition-opacity"
                ><X className="w-3.5 h-3.5" /></button>
                <div className="flex items-center justify-between pr-5">
                  <span className="font-medium text-foreground">{s.date}</span>
                  <span className={`font-mono font-bold tabular-nums ${s.diffPct > 0 ? "text-amber-400" : "text-brand"}`}>
                    {s.diffPct > 0 ? "+" : ""}{s.diffPct}%
                  </span>
                </div>
                <p className="text-muted-foreground">{s.temp}&#176;C · {s.humidity}% RH · AQI {s.aqi}</p>
                <p className="text-muted-foreground">Peak {s.peakMW} MW · Avg {s.avgMW} MW</p>
                <button
                  onClick={() => loadScenario(s)}
                  className="text-brand hover:underline mt-1"
                >Load params</button>
              </div>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
