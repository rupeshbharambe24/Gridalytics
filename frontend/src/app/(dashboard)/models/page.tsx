"use client";

import { motion } from "framer-motion";
import { BarChart3, CheckCircle2, Cpu, Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useFetch } from "@/lib/hooks";
import { getModelPerformance, getAvailableModels } from "@/lib/api";

// Known CV metrics per model (from training runs - these are validated results)
const CV_METRICS: Record<string, { mape: string; rmse: string; r2: string; folds: number; type: string }> = {
  "5min_lightgbm": { mape: "0.18%", rmse: "8.6 MW", r2: "0.9997", folds: 10, type: "Gradient Boosting" },
  "hourly_xgboost": { mape: "0.52%", rmse: "25.3 MW", r2: "0.9987", folds: 12, type: "Gradient Boosting" },
  "hourly_lightgbm": { mape: "0.62%", rmse: "30.2 MW", r2: "0.9985", folds: 12, type: "Gradient Boosting" },
  "daily_lightgbm": { mape: "2.65%", rmse: "96.6 MW", r2: "0.8997", folds: 12, type: "Gradient Boosting" },
  "daily_sarimax": { mape: "4.18%", rmse: "---", r2: "---", folds: 0, type: "Statistical (ARIMA)" },
  "hourly_lstm": { mape: "6.66%", rmse: "327.2 MW", r2: "0.7013", folds: 0, type: "Deep Learning (PyTorch)" },
  "daily_neuralprophet": { mape: "7.68%", rmse: "---", r2: "---", folds: 0, type: "Neural + Decomposition" },
};

// Champion models by resolution
const CHAMPIONS = new Set(["5min_lightgbm", "hourly_xgboost", "daily_lightgbm"]);

export default function ModelsPage() {
  const { data: perf, loading: perfLoading } = useFetch(getModelPerformance);
  const { data: available } = useFetch(getAvailableModels);

  const allModels = perf?.all_models || [];
  const trackedDays = perf?.champion?.tracked_days || 0;
  const rollingMape = perf?.champion?.hourly_mape;

  // Build display list: merge API model data with known CV metrics
  const displayModels = allModels.map((m: any) => {
    const key = `${m.resolution}_${m.name}`;
    const cv = CV_METRICS[key];
    return {
      ...m,
      mape: cv?.mape || "---",
      rmse: cv?.rmse || "---",
      r2: cv?.r2 || "---",
      folds: cv?.folds || 0,
      type: cv?.type || "Unknown",
      isChampion: CHAMPIONS.has(key),
    };
  });

  // Sort: champions first, then by MAPE
  displayModels.sort((a: any, b: any) => {
    if (a.isChampion && !b.isChampion) return -1;
    if (!a.isChampion && b.isChampion) return 1;
    const aMape = parseFloat(a.mape) || 999;
    const bMape = parseFloat(b.mape) || 999;
    return aMape - bMape;
  });

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Model Performance</h1>
        <p className="text-sm text-muted-foreground mt-0.5">
          {allModels.length} trained models across {new Set(allModels.map((m: any) => m.resolution)).size} resolutions
          {trackedDays > 0 && ` | ${trackedDays} days of live tracking`}
          {rollingMape && ` | Rolling MAPE: ${rollingMape}%`}
        </p>
      </motion.div>

      {/* Loading */}
      {perfLoading && (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Model Cards (from API) */}
      {!perfLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {displayModels.map((m: any, i: number) => (
            <motion.div
              key={`${m.name}-${m.resolution}`}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07 }}
              className="rounded-xl border border-border bg-card p-5 space-y-4 hover:border-blue-500/30 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-semibold text-foreground">{m.name}</h3>
                  <p className="text-xs text-muted-foreground">{m.resolution} resolution | {m.type}</p>
                </div>
                <Badge
                  variant={m.isChampion ? "default" : "outline"}
                  className={m.isChampion ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : ""}
                >
                  {m.isChampion ? (
                    <span className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Champion</span>
                  ) : "Challenger"}
                </Badge>
              </div>

              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: "MAPE", value: m.mape, highlight: true },
                  { label: "RMSE", value: m.rmse },
                  { label: "R2", value: m.r2 },
                  { label: "Size", value: `${m.size_mb} MB` },
                ].map((metric) => (
                  <div key={metric.label} className="rounded-lg bg-accent/30 p-2.5">
                    <p className="text-[10px] text-muted-foreground uppercase">{metric.label}</p>
                    <p className={`text-sm font-bold font-mono mt-0.5 ${metric.highlight ? "text-blue-400" : "text-foreground"}`}>
                      {metric.value}
                    </p>
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border">
                <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> {m.features} features</span>
                <span className="flex items-center gap-1"><BarChart3 className="w-3 h-3" /> {m.folds > 0 ? `${m.folds}-fold CV` : "Holdout eval"}</span>
                {m.is_loaded && <Badge variant="outline" className="text-[9px] bg-emerald-500/10 text-emerald-400 border-emerald-500/20">Loaded</Badge>}
              </div>
            </motion.div>
          ))}
        </div>
      )}

      {/* Comparison with Old EDFS */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="p-5 border-b border-border">
          <h3 className="font-semibold">Comparison vs Old EDFS</h3>
          <p className="text-xs text-muted-foreground mt-0.5">Previous project used a single SARIMAX model with data leakage</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-xs text-muted-foreground border-b border-border">
                <th className="text-left p-4 font-medium">Metric</th>
                <th className="text-center p-4 font-medium">Old SARIMAX</th>
                <th className="text-center p-4 font-medium">New 5-Min</th>
                <th className="text-center p-4 font-medium">New Hourly</th>
                <th className="text-center p-4 font-medium">New Daily</th>
                <th className="text-center p-4 font-medium">Improvement</th>
              </tr>
            </thead>
            <tbody>
              {[
                { metric: "MAPE", old: "24.77%", new5: "0.18%", newH: "0.52%", newD: "2.65%", imp: "137x better" },
                { metric: "R2", old: "-0.04", new5: "0.9997", newH: "0.9987", newD: "0.8997", imp: "Negative to 99.97%" },
                { metric: "RMSE", old: "1,373 MW", new5: "8.6 MW", newH: "25.3 MW", newD: "96.6 MW", imp: "159x smaller" },
                { metric: "Model Size", old: "~400 MB", new5: "8.1 MB", newH: "24.5 MB", newD: "3.0 MB", imp: "49x smaller" },
                { metric: "Features", old: "4", new5: "90", newH: "93", newD: "99", imp: "+86-95 features" },
                { metric: "Validation", old: "None (leak)", new5: "10-fold CV", newH: "12-fold CV", newD: "12-fold CV", imp: "Proper methodology" },
              ].map((row) => (
                <tr key={row.metric} className="border-b border-border/50 hover:bg-accent/20 transition-colors">
                  <td className="p-4 font-medium">{row.metric}</td>
                  <td className="p-4 text-center font-mono text-rose-400">{row.old}</td>
                  <td className="p-4 text-center font-mono text-blue-400 font-bold">{row.new5}</td>
                  <td className="p-4 text-center font-mono text-emerald-400">{row.newH}</td>
                  <td className="p-4 text-center font-mono text-emerald-400">{row.newD}</td>
                  <td className="p-4 text-center">
                    <Badge variant="outline" className="text-xs bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                      {row.imp}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </motion.div>

      {/* Loaded Models */}
      {available && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.5 }}
          className="flex items-center gap-3 text-xs text-muted-foreground"
        >
          <span>Currently loaded in API:</span>
          {Object.entries(available).map(([key, name]) => (
            <Badge key={key} variant="outline" className="font-mono">{key}</Badge>
          ))}
        </motion.div>
      )}
    </div>
  );
}
