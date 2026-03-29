"use client";

import { motion } from "framer-motion";
import { BarChart3, CheckCircle2, Clock, Cpu, HardDrive } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useFetch } from "@/lib/hooks";
import { getModelPerformance, getAvailableModels } from "@/lib/api";

const modelDetails = [
  {
    name: "LightGBM",
    resolution: "5-Minute",
    mape: "0.18%",
    rmse: "8.6 MW",
    r2: "0.9997",
    size: "8.1 MB",
    status: "champion",
    features: 90,
    folds: 10,
    type: "Gradient Boosting",
  },
  {
    name: "XGBoost",
    resolution: "Hourly",
    mape: "0.52%",
    rmse: "25.3 MW",
    r2: "0.9987",
    size: "24.5 MB",
    status: "champion",
    features: 93,
    folds: 12,
    type: "Gradient Boosting",
  },
  {
    name: "LightGBM",
    resolution: "Daily",
    mape: "2.65%",
    rmse: "96.6 MW",
    r2: "0.8997",
    size: "3.0 MB",
    status: "champion",
    features: 99,
    folds: 12,
    type: "Gradient Boosting",
  },
  {
    name: "LightGBM",
    resolution: "Hourly",
    mape: "0.62%",
    rmse: "30.2 MW",
    r2: "0.9985",
    size: "~5 MB",
    status: "challenger",
    features: 93,
    folds: 12,
    type: "Gradient Boosting",
  },
  {
    name: "SARIMAX",
    resolution: "Daily",
    mape: "4.18%",
    rmse: "---",
    r2: "---",
    size: "~2 MB",
    status: "challenger",
    features: 4,
    folds: 0,
    type: "Statistical (ARIMA)",
  },
  {
    name: "BiLSTM",
    resolution: "Hourly",
    mape: "6.66%",
    rmse: "327.2 MW",
    r2: "0.7013",
    size: "0.7 MB",
    status: "challenger",
    features: 93,
    folds: 0,
    type: "Deep Learning (PyTorch)",
  },
  {
    name: "NeuralProphet",
    resolution: "Daily",
    mape: "7.68%",
    rmse: "---",
    r2: "---",
    size: "~5 MB",
    status: "challenger",
    features: 5,
    folds: 0,
    type: "Neural + Decomposition",
  },
];

const oldModel = {
  name: "SARIMAX (Old EDFS)",
  mape: "24.77%",
  r2: "-0.04",
  size: "~400 MB",
  features: 4,
  validation: "None (data leakage)",
};

export default function ModelsPage() {
  const { data: available } = useFetch(getAvailableModels);

  return (
    <div className="space-y-6">
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <h1 className="text-2xl font-bold tracking-tight">Model Performance</h1>
        <p className="text-sm text-muted-foreground mt-0.5">Compare trained models and their metrics</p>
      </motion.div>

      {/* Model Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
        {modelDetails.map((m, i) => (
          <motion.div
            key={`${m.name}-${m.resolution}`}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="rounded-xl border border-border bg-card p-5 space-y-4 hover:border-blue-500/30 transition-colors"
          >
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-foreground">{m.name}</h3>
                <p className="text-xs text-muted-foreground">{m.resolution} Resolution</p>
              </div>
              <Badge
                variant={m.status === "champion" ? "default" : "outline"}
                className={m.status === "champion" ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : ""}
              >
                {m.status === "champion" ? (
                  <span className="flex items-center gap-1"><CheckCircle2 className="w-3 h-3" /> Champion</span>
                ) : "Challenger"}
              </Badge>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-3">
              {[
                { label: "MAPE", value: m.mape, highlight: true },
                { label: "RMSE", value: m.rmse },
                { label: "R²", value: m.r2 },
                { label: "Model Size", value: m.size },
              ].map((metric) => (
                <div key={metric.label} className="rounded-lg bg-accent/30 p-2.5">
                  <p className="text-[10px] text-muted-foreground uppercase">{metric.label}</p>
                  <p className={`text-sm font-bold font-mono mt-0.5 ${metric.highlight ? "text-blue-400" : "text-foreground"}`}>
                    {metric.value}
                  </p>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t border-border">
              <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> {m.features} features</span>
              <span className="flex items-center gap-1"><BarChart3 className="w-3 h-3" /> {m.folds}-fold CV</span>
            </div>
          </motion.div>
        ))}
      </div>

      {/* Comparison with Old EDFS (legacy project name kept intentionally) */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="p-5 border-b border-border">
          <h3 className="font-semibold">Comparison vs Old EDFS</h3>
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
                { metric: "MAPE", old: "24.77%", new5: "0.18%", newH: "0.52%", newD: "2.65%", imp: "~137x better" },
                { metric: "R2", old: "-0.04", new5: "0.9997", newH: "0.9987", newD: "0.8997", imp: "Negative to 99.97%" },
                { metric: "RMSE", old: "1,373 MW", new5: "8.6 MW", newH: "25.3 MW", newD: "96.6 MW", imp: "159x smaller error" },
                { metric: "Model Size", old: "~400 MB", new5: "8.1 MB", newH: "24.5 MB", newD: "3.0 MB", imp: "49x smaller" },
                { metric: "Features", old: "4", new5: "90", newH: "93", newD: "99", imp: "+86-95 features" },
                { metric: "Validation", old: "None", new5: "10-fold CV", newH: "12-fold CV", newD: "12-fold CV", imp: "Proper methodology" },
              ].map((row, i) => (
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

      {/* Available Models */}
      {available && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="flex items-center gap-3 text-xs text-muted-foreground"
        >
          <span>Loaded Models:</span>
          {Object.entries(available).map(([key, name]) => (
            <Badge key={key} variant="outline" className="font-mono">{key}</Badge>
          ))}
        </motion.div>
      )}
    </div>
  );
}
