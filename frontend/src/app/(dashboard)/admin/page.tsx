"use client";

import { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Settings, RefreshCw, Play, Cpu, HardDrive, Clock,
  Database, CheckCircle2, AlertTriangle, XCircle, Loader2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useFetch } from "@/lib/hooks";
import {
  getAdminModels,
  triggerRetrain,
  getRetrainStatus,
  getScraperStatus,
  getSchedulerJobs,
  getMe,
} from "@/lib/api";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ageHours(timestamp: string): number {
  return (Date.now() - new Date(timestamp).getTime()) / (1000 * 60 * 60);
}

function ageBadge(hours: number) {
  if (hours < 24) return { label: "Fresh", cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" };
  if (hours < 48) return { label: "Stale", cls: "bg-amber-500/15 text-amber-400 border-amber-500/30" };
  return { label: "Outdated", cls: "bg-red-500/15 text-red-400 border-red-500/30" };
}

function statusIcon(status: string) {
  switch (status) {
    case "idle":
      return <Clock className="w-4 h-4 text-muted-foreground" />;
    case "training":
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />;
    case "complete":
      return <CheckCircle2 className="w-4 h-4 text-emerald-400" />;
    case "error":
      return <XCircle className="w-4 h-4 text-red-400" />;
    default:
      return <Clock className="w-4 h-4 text-muted-foreground" />;
  }
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AdminPage() {
  // Auth check
  const { data: me, loading: authLoading, error: authError } = useFetch(getMe);
  const isAdmin = me?.role === "admin";

  // Data fetches
  const { data: models, loading: modelsLoading } = useFetch(getAdminModels);
  const { data: scraper, loading: scraperLoading } = useFetch(getScraperStatus);
  const { data: jobs, loading: jobsLoading } = useFetch(getSchedulerJobs);

  // Retrain controls
  const [resolution, setResolution] = useState("hourly");
  const [retrainLoading, setRetrainLoading] = useState(false);
  const [retrainError, setRetrainError] = useState<string | null>(null);
  const [retrainResult, setRetrainResult] = useState<string | null>(null);

  // Retrain status polling
  const [retrainStatus, setRetrainStatus] = useState<{ status: string; resolution: string | null }>({
    status: "idle",
    resolution: null,
  });

  const pollStatus = useCallback(async () => {
    try {
      const s = await getRetrainStatus();
      setRetrainStatus(s);
    } catch {
      // silently ignore polling errors
    }
  }, []);

  // Poll retrain status every 5s while training
  useEffect(() => {
    pollStatus();
    const id = setInterval(pollStatus, 5000);
    return () => clearInterval(id);
  }, [pollStatus]);

  const handleRetrain = async () => {
    setRetrainLoading(true);
    setRetrainError(null);
    setRetrainResult(null);
    try {
      const res = await triggerRetrain(resolution);
      setRetrainResult(res.status);
      pollStatus();
    } catch (err: any) {
      setRetrainError(err.message || "Retrain failed");
    } finally {
      setRetrainLoading(false);
    }
  };

  // Scraper rows
  const scraperRows: { source: string; latest: string; rows: number }[] = [];
  if (scraper) {
    Object.entries(scraper).forEach(([key, val]: [string, any]) => {
      if (val && typeof val === "object" && val.latest_timestamp) {
        scraperRows.push({
          source: key,
          latest: val.latest_timestamp,
          rows: val.row_count ?? val.total_rows ?? 0,
        });
      }
    });
  }

  // Access denied states
  if (authLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> Checking permissions...
        </div>
      </div>
    );
  }

  if (authError || !isAdmin) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="text-center space-y-3">
          <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-red-500/10 mx-auto">
            <XCircle className="w-6 h-6 text-red-400" />
          </div>
          <h2 className="text-xl font-bold text-foreground">Access Denied</h2>
          <p className="text-sm text-muted-foreground max-w-sm">
            {authError ? "Please log in as admin to access this page." : "You do not have admin privileges to view this page."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }}>
        <div className="flex items-center gap-2">
          <Settings className="w-5 h-5 text-muted-foreground" />
          <h1 className="text-2xl font-bold tracking-tight">Admin Panel</h1>
        </div>
        <p className="text-sm text-muted-foreground mt-0.5">
          Model management, retraining, and pipeline monitoring
        </p>
      </motion.div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 1: Trained Models                                         */}
      {/* ----------------------------------------------------------------- */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.05 }}
      >
        <h2 className="text-lg font-semibold mb-3">Trained Models</h2>
        {modelsLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading models...
          </div>
        ) : models && models.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {models.map((m: any, i: number) => (
              <motion.div
                key={m.name ?? i}
                initial={{ opacity: 0, y: 15 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.08 }}
                className="rounded-xl border border-border bg-card p-5 space-y-3 hover:border-blue-500/30 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <h3 className="font-semibold text-foreground">{m.name ?? "Unknown"}</h3>
                  <Badge variant="outline" className="text-xs">
                    {m.resolution ?? "N/A"}
                  </Badge>
                </div>
                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    { label: "Resolution", value: m.resolution ?? "N/A", icon: Clock },
                    { label: "Size", value: m.size ?? m.file_size ?? "N/A", icon: HardDrive },
                    { label: "Features", value: m.feature_count ?? m.features ?? "N/A", icon: Cpu },
                    { label: "Status", value: m.status ?? "loaded", icon: CheckCircle2 },
                  ].map((item) => (
                    <div key={item.label} className="rounded-lg bg-accent/30 p-2.5">
                      <p className="text-[10px] text-muted-foreground uppercase flex items-center gap-1">
                        <item.icon className="w-3 h-3" />
                        {item.label}
                      </p>
                      <p className="text-sm font-medium font-mono mt-0.5 text-foreground">
                        {String(item.value)}
                      </p>
                    </div>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No models found.</p>
        )}
      </motion.div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 2: Retrain Controls                                       */}
      {/* ----------------------------------------------------------------- */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="rounded-xl border border-border bg-card p-5 space-y-4"
      >
        <h2 className="text-lg font-semibold">Retrain Controls</h2>

        <div className="flex flex-wrap items-center gap-4">
          {/* Resolution selector */}
          <div className="flex items-center gap-2">
            <label className="text-sm text-muted-foreground">Resolution:</label>
            <div className="flex rounded-lg bg-accent/50 p-0.5">
              {["5min", "hourly", "daily"].map((r) => (
                <button
                  key={r}
                  onClick={() => setResolution(r)}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md transition-all ${
                    resolution === r
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {r === "5min" ? "5-Minute" : r.charAt(0).toUpperCase() + r.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Retrain button */}
          <Button
            onClick={handleRetrain}
            disabled={retrainLoading || retrainStatus.status === "training"}
            className="gap-2"
          >
            {retrainLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Retrain Now
          </Button>

          {/* Status indicator */}
          <div className="flex items-center gap-2 text-sm">
            {statusIcon(retrainStatus.status)}
            <span className="capitalize text-foreground">{retrainStatus.status}</span>
            {retrainStatus.resolution && (
              <span className="text-muted-foreground">({retrainStatus.resolution})</span>
            )}
          </div>
        </div>

        {/* Result/Error messages */}
        {retrainResult && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400 text-sm">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            {retrainResult}
          </div>
        )}
        {retrainError && (
          <div className="flex items-center gap-2 p-3 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-sm">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            {retrainError}
          </div>
        )}
      </motion.div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 3: Data Pipeline Status                                   */}
      {/* ----------------------------------------------------------------- */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.25 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="p-5 border-b border-border">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Database className="w-5 h-5 text-muted-foreground" />
            Data Pipeline Status
          </h2>
        </div>
        {scraperLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-5">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading pipeline status...
          </div>
        ) : scraperRows.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-border">
                  <th className="text-left p-4 font-medium">Data Source</th>
                  <th className="text-left p-4 font-medium">Latest Timestamp</th>
                  <th className="text-center p-4 font-medium">Age (hrs)</th>
                  <th className="text-center p-4 font-medium">Row Count</th>
                  <th className="text-center p-4 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {scraperRows.map((row) => {
                  const hours = ageHours(row.latest);
                  const badge = ageBadge(hours);
                  return (
                    <tr
                      key={row.source}
                      className="border-b border-border/50 hover:bg-accent/20 transition-colors"
                    >
                      <td className="p-4 font-medium capitalize">{row.source.replace(/_/g, " ")}</td>
                      <td className="p-4 font-mono text-muted-foreground text-xs">
                        {new Date(row.latest).toLocaleString("en-IN")}
                      </td>
                      <td className="p-4 text-center font-mono">{hours.toFixed(1)}</td>
                      <td className="p-4 text-center font-mono">{row.rows.toLocaleString()}</td>
                      <td className="p-4 text-center">
                        <Badge variant="outline" className={`text-xs ${badge.cls}`}>
                          {badge.label}
                        </Badge>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground p-5">No pipeline data available.</p>
        )}
      </motion.div>

      {/* ----------------------------------------------------------------- */}
      {/* Section 4: Scheduler Jobs                                         */}
      {/* ----------------------------------------------------------------- */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35 }}
        className="rounded-xl border border-border bg-card overflow-hidden"
      >
        <div className="p-5 border-b border-border">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <RefreshCw className="w-5 h-5 text-muted-foreground" />
            Scheduler Jobs
          </h2>
        </div>
        {jobsLoading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground p-5">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading jobs...
          </div>
        ) : jobs && jobs.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-muted-foreground border-b border-border">
                  <th className="text-left p-4 font-medium">Job Name</th>
                  <th className="text-left p-4 font-medium">Trigger</th>
                  <th className="text-left p-4 font-medium">Interval</th>
                  <th className="text-left p-4 font-medium">Description</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job: any, i: number) => (
                  <tr
                    key={job.name ?? i}
                    className="border-b border-border/50 hover:bg-accent/20 transition-colors"
                  >
                    <td className="p-4 font-medium">{job.name ?? job.job_name ?? "Unknown"}</td>
                    <td className="p-4">
                      <Badge variant="outline" className="text-xs">
                        {job.trigger ?? job.trigger_type ?? "N/A"}
                      </Badge>
                    </td>
                    <td className="p-4 font-mono text-muted-foreground">
                      {job.interval ?? job.schedule ?? "N/A"}
                    </td>
                    <td className="p-4 text-muted-foreground">
                      {job.description ?? "No description"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground p-5">No scheduler jobs found.</p>
        )}
      </motion.div>
    </div>
  );
}
