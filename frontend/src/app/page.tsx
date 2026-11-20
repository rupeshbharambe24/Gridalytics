"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Zap, ArrowRight, TrendingUp, Map, FlaskConical, BarChart3,
  Target, GitBranch, Database, Cpu, LineChart, ShieldCheck, Gauge,
  CheckCircle2, Clock, Layers,
} from "lucide-react";

const REPO = "https://github.com/rupeshbharambe24/Gridalytics";
const SHOWCASE = "https://rupeshbharambe24.github.io/Gridalytics/";

// lucide-react dropped brand icons, so the GitHub mark is an inline SVG.
function Github({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M12 .5C5.73.5.5 5.74.5 12.02c0 5.1 3.29 9.42 7.86 10.95.58.1.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.53-1.34-1.3-1.7-1.3-1.7-1.06-.72.08-.71.08-.71 1.17.08 1.78 1.2 1.78 1.2 1.04 1.79 2.74 1.27 3.41.97.11-.76.41-1.27.74-1.56-2.55-.29-5.23-1.28-5.23-5.7 0-1.26.45-2.29 1.19-3.1-.12-.29-.52-1.46.11-3.05 0 0 .97-.31 3.18 1.18a11.05 11.05 0 0 1 5.8 0c2.2-1.49 3.17-1.18 3.17-1.18.63 1.59.23 2.76.11 3.05.74.81 1.19 1.84 1.19 3.1 0 4.43-2.69 5.41-5.25 5.69.42.37.79 1.09.79 2.2 0 1.59-.01 2.87-.01 3.26 0 .31.21.67.8.56A11.53 11.53 0 0 0 23.5 12.02C23.5 5.74 18.27.5 12 .5Z" />
    </svg>
  );
}

// Headline metrics — the real, documented fleet numbers (docs/state_models.md,
// leak-free CV in the data-integrity audit). Static so the landing loads fast
// and renders correctly even when the API is not running.
const METRICS = [
  { value: "24", label: "Production models", sub: "national + state grids" },
  { value: "36", label: "States & UTs mapped", sub: "SLDC + Grid-India fallback" },
  { value: "3", label: "Resolutions", sub: "5-min · hourly · daily" },
  { value: "~92%", label: "Interval coverage", sub: "conformal-calibrated" },
];

// Leak-free day-ahead accuracy for the Delhi reference grid (walk-forward CV),
// champion model vs the persistence baseline. Lower MAPE is better.
const ACCURACY = [
  { res: "Daily (peak)", model: "3.92%", base: "5.05%", champ: "LightGBM" },
  { res: "Hourly", model: "1.31%", base: "3.43%", champ: "LightGBM" },
  { res: "5-minute", model: "0.45%", base: "0.68%", champ: "XGBoost" },
];

const FEATURES = [
  {
    icon: TrendingUp, href: "/forecast", title: "Day-ahead forecasts",
    body: "Recursive multi-horizon predictions with conformal prediction intervals you can actually trust — recalibrated to ~92% empirical coverage.",
  },
  {
    icon: Map, href: "/states", title: "All-India state fleet",
    body: "36 states and UTs mapped, 24 grids with trained models — each with its own data source, scraper tier and live collection status.",
  },
  {
    icon: FlaskConical, href: "/what-if", title: "What-if scenarios",
    body: "Push temperature, holidays and demand overrides, then compare several scenarios side-by-side against the baseline forecast.",
  },
  {
    icon: BarChart3, href: "/models", title: "Model performance",
    body: "Champion/challenger walk-forward cross-validation over LightGBM and XGBoost — every served model earns its place by lowest MAPE.",
  },
  {
    icon: Target, href: "/accuracy", title: "Accuracy tracking",
    body: "Predicted-vs-actual logged daily, with rolling MAPE and interval coverage so forecast quality is measured in the open, not asserted.",
  },
  {
    icon: LineChart, href: "/analytics", title: "Demand analytics",
    body: "Load profiles, seasonal structure, weather sensitivity and festival demand shocks — the signals the models learn from, made visible.",
  },
];

const PIPELINE = [
  { icon: Database, title: "Collect", body: "Per-state SLDC scrapers + a Grid-India daily-PSP fallback, Open-Meteo weather/AQI and the Indian holiday calendar." },
  { icon: Layers, title: "Engineer", body: "~93 leak-free features — temporal, weather, calendar and rolling stats that end strictly at t−1, so nothing leaks the target." },
  { icon: Cpu, title: "Select", body: "Champion/challenger walk-forward CV picks the lowest-MAPE model per state and resolution, with classical challengers for a sanity floor." },
  { icon: Gauge, title: "Serve", body: "FastAPI serves day-ahead forecasts with calibrated intervals; models hot-reload without a restart as new grids come online." },
];

function useScrolled() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  return scrolled;
}

export default function LandingPage() {
  const scrolled = useScrolled();

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* ---- Nav ---- */}
      <header
        className={`sticky top-0 z-50 transition-colors ${
          scrolled ? "bg-background/80 backdrop-blur-md border-b border-border" : "bg-transparent"
        }`}
      >
        <nav className="max-w-6xl mx-auto flex items-center gap-4 px-4 lg:px-6 h-16">
          <Link href="/" className="flex items-center gap-2.5 mr-auto">
            <span className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-gradient shadow-brand">
              <Zap className="w-5 h-5 text-white" strokeWidth={2.5} />
            </span>
            <span className="font-bold tracking-tight text-[15px]">Gridalytics</span>
          </Link>
          <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
            <a href="#features" className="hover:text-foreground transition-colors">Features</a>
            <a href="#how" className="hover:text-foreground transition-colors">How it works</a>
            <a href="#accuracy" className="hover:text-foreground transition-colors">Accuracy</a>
            <a href={REPO} target="_blank" rel="noopener noreferrer" className="hover:text-foreground transition-colors flex items-center gap-1.5">
              <Github className="w-4 h-4" /> GitHub
            </a>
          </div>
          <Link
            href="/dashboard"
            className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-3.5 py-2 text-sm font-medium text-brand-foreground hover:opacity-90 transition-opacity"
          >
            Open dashboard <ArrowRight className="w-4 h-4" />
          </Link>
        </nav>
      </header>

      {/* ---- Hero ---- */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 bg-grid [mask-image:radial-gradient(ellipse_at_top,black,transparent_72%)]" aria-hidden />
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[640px] h-[640px] rounded-full bg-brand/10 blur-[120px]" aria-hidden />
        <div className="relative max-w-6xl mx-auto px-4 lg:px-6 pt-20 pb-20 lg:pt-28 lg:pb-28">
          <motion.div
            initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5 }}
            className="max-w-3xl"
          >
            <span className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-xs font-medium text-brand">
              <span className="w-1.5 h-1.5 rounded-full bg-brand animate-pulse" />
              Electricity-demand forecasting for India
            </span>
            <h1 className="mt-5 text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight text-balance leading-[1.05]">
              Forecasting India's grid,
              <span className="text-gradient-brand"> state by state.</span>
            </h1>
            <p className="mt-5 text-lg text-muted-foreground max-w-2xl leading-relaxed">
              Gridalytics turns raw SLDC feeds, weather and the festival calendar into
              calibrated day-ahead demand forecasts — at 5-minute, hourly and daily
              resolution — across 36 states and union territories.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/dashboard"
                className="inline-flex items-center gap-2 rounded-xl bg-brand px-5 py-3 text-sm font-semibold text-brand-foreground shadow-brand hover:opacity-90 transition-opacity"
              >
                Open the dashboard <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/states"
                className="inline-flex items-center gap-2 rounded-xl border border-border bg-card px-5 py-3 text-sm font-semibold hover:bg-accent transition-colors"
              >
                <Map className="w-4 h-4" /> Explore the state fleet
              </Link>
              <a
                href={SHOWCASE} target="_blank" rel="noopener noreferrer"
                className="inline-flex items-center gap-2 rounded-xl px-4 py-3 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
              >
                Pipeline walkthrough
              </a>
            </div>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
              <span className="flex items-center gap-1.5"><ShieldCheck className="w-4 h-4 text-chart-good" /> Leak-free walk-forward CV</span>
              <span className="flex items-center gap-1.5"><CheckCircle2 className="w-4 h-4 text-chart-good" /> Conformal prediction intervals</span>
              <span className="flex items-center gap-1.5"><GitBranch className="w-4 h-4 text-chart-good" /> Open source · contributions welcome</span>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ---- Metrics band ---- */}
      <section className="border-y border-border bg-card/40">
        <div className="max-w-6xl mx-auto px-4 lg:px-6 py-8 grid grid-cols-2 lg:grid-cols-4 gap-6">
          {METRICS.map((m, i) => (
            <motion.div
              key={m.label}
              initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ duration: 0.4, delay: i * 0.05 }}
            >
              <div className="text-3xl lg:text-4xl font-bold tracking-tight tabular-nums text-foreground">{m.value}</div>
              <div className="text-sm font-medium mt-1">{m.label}</div>
              <div className="text-xs text-muted-foreground mt-0.5">{m.sub}</div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ---- Features ---- */}
      <section id="features" className="max-w-6xl mx-auto px-4 lg:px-6 py-20 lg:py-24">
        <div className="max-w-2xl">
          <h2 className="text-3xl font-bold tracking-tight text-balance">Everything the grid team needs, in one place</h2>
          <p className="mt-3 text-muted-foreground">
            Not a single chart — a full forecasting platform. Every section below is a live page you can open.
          </p>
        </div>
        <div className="mt-10 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }} transition={{ duration: 0.4, delay: (i % 3) * 0.06 }}
            >
              <Link
                href={f.href}
                className="group block h-full rounded-2xl border border-border bg-card p-6 shadow-card hover:border-brand/40 hover:-translate-y-0.5 transition-all"
              >
                <div className="w-11 h-11 rounded-xl bg-brand/10 flex items-center justify-center">
                  <f.icon className="w-[22px] h-[22px] text-brand" />
                </div>
                <h3 className="mt-4 font-semibold flex items-center gap-1.5">
                  {f.title}
                  <ArrowRight className="w-4 h-4 text-muted-foreground opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all" />
                </h3>
                <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{f.body}</p>
              </Link>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ---- How it works ---- */}
      <section id="how" className="border-y border-border bg-card/40">
        <div className="max-w-6xl mx-auto px-4 lg:px-6 py-20 lg:py-24">
          <div className="max-w-2xl">
            <h2 className="text-3xl font-bold tracking-tight text-balance">From SLDC feed to calibrated forecast</h2>
            <p className="mt-3 text-muted-foreground">
              An automated pipeline that onboards each state as its data comes online.
            </p>
          </div>
          <div className="mt-10 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {PIPELINE.map((s, i) => (
              <motion.div
                key={s.title}
                initial={{ opacity: 0, y: 12 }} whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }} transition={{ duration: 0.4, delay: i * 0.06 }}
                className="relative rounded-2xl border border-border bg-background p-6"
              >
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono text-brand">0{i + 1}</span>
                  <s.icon className="w-5 h-5 text-brand" />
                </div>
                <h3 className="mt-3 font-semibold">{s.title}</h3>
                <p className="mt-1.5 text-sm text-muted-foreground leading-relaxed">{s.body}</p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* ---- Accuracy ---- */}
      <section id="accuracy" className="max-w-6xl mx-auto px-4 lg:px-6 py-20 lg:py-24">
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_1.1fr] gap-10 lg:gap-16 items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight text-balance">Accuracy measured in the open</h2>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Every number is from leak-free, walk-forward cross-validation — diff and
              rolling features end strictly at t−1, so the model never sees the value
              it is predicting. These are the Delhi reference grid's day-ahead results,
              champion model versus a same-horizon persistence baseline.
            </p>
            <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
              <span className="flex items-center gap-1.5"><Clock className="w-4 h-4 text-brand" /> Day-ahead horizon</span>
              <span className="flex items-center gap-1.5"><Cpu className="w-4 h-4 text-brand" /> LightGBM · XGBoost champions</span>
            </div>
          </div>
          <div className="rounded-2xl border border-border bg-card shadow-card overflow-hidden">
            <div className="grid grid-cols-[1.4fr_1fr_1fr] text-xs font-medium text-muted-foreground px-5 py-3 border-b border-border bg-muted/30">
              <span>Resolution</span>
              <span className="text-right">Gridalytics</span>
              <span className="text-right">Persistence</span>
            </div>
            {ACCURACY.map((row) => (
              <div key={row.res} className="grid grid-cols-[1.4fr_1fr_1fr] items-baseline px-5 py-4 border-b border-border last:border-0">
                <div>
                  <div className="font-medium text-sm">{row.res}</div>
                  <div className="text-[11px] text-muted-foreground font-mono">{row.champ}</div>
                </div>
                <div className="text-right font-semibold tabular-nums text-chart-good">{row.model}</div>
                <div className="text-right tabular-nums text-muted-foreground">{row.base}</div>
              </div>
            ))}
            <p className="px-5 py-3 text-[11px] text-muted-foreground">
              MAPE — lower is better. Prediction intervals recalibrated to ~92% empirical coverage.
            </p>
          </div>
        </div>
      </section>

      {/* ---- Open source CTA ---- */}
      <section className="border-t border-border bg-card/40">
        <div className="max-w-6xl mx-auto px-4 lg:px-6 py-16 lg:py-20">
          <div className="rounded-3xl border border-brand/30 bg-brand/5 p-8 lg:p-12 text-center relative overflow-hidden">
            <div className="absolute inset-0 bg-grid opacity-50 [mask-image:radial-gradient(ellipse_at_center,black,transparent_70%)]" aria-hidden />
            <div className="relative">
              <h2 className="text-3xl font-bold tracking-tight text-balance">Built in the open</h2>
              <p className="mt-3 text-muted-foreground max-w-2xl mx-auto leading-relaxed">
                Gridalytics is open source. Browse the code, open an issue, or pick up one
                of the good-first issues — contributions to the forecasting fleet and the
                dashboard are welcome.
              </p>
              <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
                <a
                  href={REPO} target="_blank" rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 rounded-xl bg-foreground px-5 py-3 text-sm font-semibold text-background hover:opacity-90 transition-opacity"
                >
                  <Github className="w-4 h-4" /> View on GitHub
                </a>
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-5 py-3 text-sm font-semibold hover:bg-accent transition-colors"
                >
                  Open the dashboard <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---- Footer ---- */}
      <footer className="border-t border-border">
        <div className="max-w-6xl mx-auto px-4 lg:px-6 py-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-muted-foreground">
          <p>&copy; {new Date().getFullYear()} Rupesh Bharambe. All rights reserved.</p>
          <p className="flex items-center gap-1.5">
            <Zap className="w-3.5 h-3.5 text-brand" />
            <span className="font-semibold text-foreground">Gridalytics</span>
            <span>—</span>
            <span>AI-powered grid intelligence</span>
          </p>
        </div>
      </footer>
    </div>
  );
}
