"use client";

import { motion } from "framer-motion";
import { Info, Zap, Clock, BarChart3, Database, Brain, AlertTriangle, ExternalLink, FlaskConical } from "lucide-react";
import { Badge } from "@/components/ui/badge";

const fadeIn = (delay: number) => ({
  initial: { opacity: 0, y: 15 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.4, delay },
});

function Section({ title, icon: Icon, children, delay = 0 }: { title: string; icon: any; children: React.ReactNode; delay?: number }) {
  return (
    <motion.div {...fadeIn(delay)} className="rounded-xl border border-border bg-card p-6 space-y-4">
      <h2 className="text-lg font-semibold flex items-center gap-2.5">
        <div className="p-1.5 rounded-lg bg-blue-500/10">
          <Icon className="w-4.5 h-4.5 text-blue-400" />
        </div>
        {title}
      </h2>
      <div className="text-sm text-muted-foreground leading-relaxed space-y-3">
        {children}
      </div>
    </motion.div>
  );
}

function UnitCard({ unit, name, meaning, example, color }: { unit: string; name: string; meaning: string; example: string; color: string }) {
  return (
    <div className={`rounded-lg border p-4 ${color}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xl font-bold font-mono">{unit}</span>
        <span className="text-xs text-muted-foreground">({name})</span>
      </div>
      <p className="text-sm text-muted-foreground">{meaning}</p>
      <p className="text-xs mt-2 font-mono bg-background/50 rounded px-2 py-1">{example}</p>
    </div>
  );
}

export default function InfoPage() {
  return (
    <div className="space-y-6 max-w-4xl">
      {/* Header */}
      <motion.div {...fadeIn(0)}>
        <h1 className="text-2xl font-bold tracking-tight">How Gridalytics Works</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Understanding electricity demand forecasting, units, and how to read the predictions
        </p>
      </motion.div>

      {/* Units Explanation */}
      <Section title="Understanding the Units" icon={Zap} delay={0.05}>
        <p>
          All demand values in Gridalytics are shown in <strong className="text-foreground">MW (Megawatts)</strong> — this is
          the standard unit used by the Delhi SLDC (State Load Despatch Centre) and the Indian power grid.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 my-4">
          <UnitCard
            unit="MW"
            name="Megawatt"
            meaning="Instantaneous power — how much electricity Delhi is consuming right now"
            example="Delhi Load: 4,200 MW at 3:00 PM"
            color="border-blue-500/20 bg-blue-500/5"
          />
          <UnitCard
            unit="MWh"
            name="Megawatt-hour"
            meaning="Energy consumed over time. 1 MWh = using 1 MW for 1 hour"
            example="Daily energy = Avg MW x 24 hours"
            color="border-emerald-500/20 bg-emerald-500/5"
          />
          <UnitCard
            unit="MU"
            name="Million Units"
            meaning="Large-scale energy measure. 1 MU = 1,000 MWh = 1 million kWh"
            example="Delhi daily: ~90-96 MU/day"
            color="border-amber-500/20 bg-amber-500/5"
          />
        </div>

        <div className="rounded-lg bg-accent/30 p-4 border border-border">
          <p className="text-xs font-medium text-foreground mb-2">Key Insight: MW is like the speedometer of the power grid</p>
          <p className="text-xs">
            Think of MW as the speed of a car (how fast energy is flowing right now) and MWh as the distance traveled (total energy consumed over time).
            When we say "demand is 4,000 MW", it means Delhi's grid is delivering 4,000 megawatts of power at that instant.
            Over a full day at that rate, it would consume 4,000 x 24 = 96,000 MWh = 96 MU of energy.
          </p>
        </div>
      </Section>

      {/* How Predictions Relate */}
      <Section title="How 5-Min, Hourly, and Daily Predictions Relate" icon={Clock} delay={0.1}>
        <p>
          All three prediction types show <strong className="text-foreground">demand in MW</strong>, but at different time scales:
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Resolution</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">What Each Value Means</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">Points/Day</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Example</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              <tr className="border-b border-border/50">
                <td className="p-2.5"><Badge variant="outline" className="text-xs">5-Minute</Badge></td>
                <td className="p-2.5">Average MW during that 5-min window</td>
                <td className="p-2.5 text-center font-mono">286</td>
                <td className="p-2.5 font-mono">5:00 AM → 2,850 MW</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5"><Badge variant="outline" className="text-xs">Hourly</Badge></td>
                <td className="p-2.5">Average MW during that hour (avg of 12 five-min readings)</td>
                <td className="p-2.5 text-center font-mono">24</td>
                <td className="p-2.5 font-mono">5:00 AM hour → 2,870 MW</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5"><Badge variant="outline" className="text-xs">Daily</Badge></td>
                <td className="p-2.5">Average MW across all 24 hours (avg of all 286 five-min readings)</td>
                <td className="p-2.5 text-center font-mono">1</td>
                <td className="p-2.5 font-mono">March 29 → 3,800 MW (avg)</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div className="rounded-lg bg-accent/30 p-4 border border-border">
          <p className="text-xs font-medium text-foreground mb-2">Why daily and hourly values look similar:</p>
          <p className="text-xs">
            If hourly predictions range from 2,500 MW (night) to 5,200 MW (afternoon peak), the daily prediction will be
            their average: ~3,800 MW. This is correct — they're both measuring the same thing (instantaneous power in MW),
            just averaged over different time periods. The daily value is NOT the sum of hourly values.
          </p>
          <div className="mt-3 font-mono text-xs space-y-1">
            <p className="text-muted-foreground">To calculate total daily energy consumption:</p>
            <p className="text-foreground">Daily Energy = Average Demand (MW) x 24 hours = MWh</p>
            <p className="text-foreground">Example: 3,800 MW x 24h = 91,200 MWh = 91.2 MU</p>
          </div>
        </div>
      </Section>

      {/* Data Source */}
      <Section title="Data Source: Delhi SLDC" icon={Database} delay={0.15}>
        <p>
          All demand data comes from the <strong className="text-foreground">Delhi State Load Despatch Centre (SLDC)</strong>,
          operated by Delhi Transco Limited (DTL). The SLDC monitors and controls the Delhi power grid in real-time.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Data</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Source</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">Interval</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Coverage</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              <tr className="border-b border-border/50">
                <td className="p-2.5">SCADA Demand</td>
                <td className="p-2.5">delhisldc.org/Loaddata.aspx</td>
                <td className="p-2.5 text-center font-mono">5 min</td>
                <td className="p-2.5">2021 - present (201K+ rows)</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5">Weather</td>
                <td className="p-2.5">Open-Meteo API (free)</td>
                <td className="p-2.5 text-center font-mono">1 hour</td>
                <td className="p-2.5">2021 - present (45K+ rows)</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5">Air Quality (AQI)</td>
                <td className="p-2.5">Open-Meteo Air Quality API</td>
                <td className="p-2.5 text-center font-mono">Daily</td>
                <td className="p-2.5">2025 - present (356 rows)</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5">Holidays</td>
                <td className="p-2.5">Python holidays lib + curated</td>
                <td className="p-2.5 text-center font-mono">Daily</td>
                <td className="p-2.5">2015 - 2026 (472 entries)</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5">Weather Forecast</td>
                <td className="p-2.5">Open-Meteo Forecast API</td>
                <td className="p-2.5 text-center font-mono">1 hour</td>
                <td className="p-2.5">Up to 16 days ahead</td>
              </tr>
            </tbody>
          </table>
        </div>

        <p>
          Delhi's power is distributed by 5 DISCOMs (distribution companies):
        </p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          {[
            { code: "BRPL", name: "BSES Rajdhani", area: "South & West" },
            { code: "BYPL", name: "BSES Yamuna", area: "Central & East" },
            { code: "TPDDL", name: "Tata Power DDL", area: "North & NW" },
            { code: "NDMC", name: "Municipal Council", area: "Lutyens' Delhi" },
            { code: "MES", name: "Military Engg.", area: "Cantonment" },
          ].map((d) => (
            <div key={d.code} className="rounded-lg bg-accent/30 p-2.5 text-center">
              <p className="font-mono text-xs font-bold text-foreground">{d.code}</p>
              <p className="text-[10px] text-muted-foreground mt-0.5">{d.area}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Models */}
      <Section title="How the AI Models Work" icon={Brain} delay={0.2}>
        <p>
          Gridalytics uses multiple machine learning models trained on <strong className="text-foreground">93 engineered features</strong> derived
          from demand history, weather, holidays, time patterns, and seasonal cycles.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Model</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Type</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">Best For</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">MAPE</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              {[
                { name: "LightGBM", type: "Gradient Boosting", best: "5-Minute", mape: "0.18%", champion: true },
                { name: "LightGBM (Optuna)", type: "Gradient Boosting", best: "Hourly", mape: "0.50%", champion: false },
                { name: "XGBoost", type: "Gradient Boosting", best: "Hourly", mape: "0.52%", champion: true },
                { name: "LightGBM", type: "Gradient Boosting", best: "Daily", mape: "2.65%", champion: true },
                { name: "SARIMAX", type: "Statistical (ARIMA)", best: "Daily", mape: "4.18%", champion: false },
                { name: "BiLSTM", type: "Deep Learning (PyTorch)", best: "Hourly", mape: "6.66%", champion: false },
                { name: "NeuralProphet", type: "Neural + Decomposition", best: "Daily", mape: "7.68%", champion: false },
              ].map((m) => (
                <tr key={m.name} className="border-b border-border/50">
                  <td className="p-2.5 font-medium text-foreground flex items-center gap-1.5">
                    {m.name}
                    {m.champion && <Badge className="text-[9px] bg-emerald-500/15 text-emerald-400 border-0">champion</Badge>}
                  </td>
                  <td className="p-2.5">{m.type}</td>
                  <td className="p-2.5 text-center">{m.best}</td>
                  <td className="p-2.5 text-center font-mono text-blue-400">{m.mape}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="text-xs">
          <strong className="text-foreground">MAPE (Mean Absolute Percentage Error)</strong> is the primary accuracy metric.
          A MAPE of 0.52% means the model's predictions are, on average, within 0.52% of the actual demand.
          For a 4,000 MW demand, that's an error of just ~21 MW.
        </p>

        <div className="rounded-lg bg-accent/30 p-4 border border-border">
          <p className="text-xs font-medium text-foreground mb-2">Feature categories (93 total):</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {[
              { group: "Lag Features", count: 5, desc: "Past demand values" },
              { group: "Rolling Stats", count: 21, desc: "Trends & volatility" },
              { group: "Weather", count: 15, desc: "Temp, humidity, solar" },
              { group: "Time Encoding", count: 18, desc: "Hour, day, season cycles" },
              { group: "Fourier Terms", count: 18, desc: "Periodic patterns" },
              { group: "Calendar", count: 11, desc: "Holidays, festivals, AQI" },
              { group: "Time Flags", count: 3, desc: "Peak, night, morning" },
              { group: "Diff Features", count: 2, desc: "Rate of change" },
            ].map((f) => (
              <div key={f.group} className="rounded bg-background/50 p-2">
                <p className="font-medium text-foreground">{f.group} ({f.count})</p>
                <p className="text-muted-foreground">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* How to Read */}
      <Section title="How to Read the Forecasts" icon={BarChart3} delay={0.25}>
        <div className="space-y-4">
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">The Blue Line (Actual Demand)</h3>
            <p className="text-xs">Shows real historical demand data from the Delhi SLDC. Only available for past dates.</p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">The Orange Dashed Line (Forecast)</h3>
            <p className="text-xs">Shows the model's predicted demand. For past dates, you can compare this with the blue line to see accuracy. For future dates, only the orange line appears.</p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">The Shaded Band (Confidence Interval)</h3>
            <p className="text-xs">Shows the 90% prediction interval — the model is 90% confident the actual demand will fall within this band. Wider bands = more uncertainty.</p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">Peak Demand</h3>
            <p className="text-xs">
              The highest predicted MW value in the forecast period. This is the most critical number for grid operators —
              the grid must have enough capacity to meet peak demand or risk blackouts. Delhi's all-time peak was
              <strong className="text-foreground"> 8,656 MW</strong> (June 19, 2024, 3:06 PM).
            </p>
          </div>
          <div>
            <h3 className="text-sm font-medium text-foreground mb-1">Total Energy (MWh / MU)</h3>
            <p className="text-xs">
              The sum of predicted demand multiplied by the time interval. For hourly forecasts:
              Total Energy = Sum of all hourly MW values (since each represents 1 hour).
              Divide by 1,000 to get MU (Million Units).
            </p>
          </div>
        </div>
      </Section>

      {/* Accuracy Tracking */}
      <Section title="Prediction Accuracy Tracking" icon={AlertTriangle} delay={0.3}>
        <p>
          Every day, Gridalytics automatically:
        </p>
        <ol className="list-decimal list-inside space-y-1 text-xs">
          <li>Predicts tomorrow's demand and records the prediction</li>
          <li>The next day, fetches the actual demand from SLDC</li>
          <li>Computes the error (MAPE) and logs it</li>
          <li>Monitors if accuracy is degrading (drift detection)</li>
        </ol>
        <p className="mt-2">
          Over the last 29 days of live tracking, the system achieved an average MAPE of
          <strong className="text-foreground"> 0.97%</strong> — meaning predictions were within 1% of actual demand on average.
        </p>
        <p className="text-xs">
          Visit the <strong className="text-foreground">Accuracy</strong> page to see the full predicted vs actual history,
          rolling MAPE trend, and drift detection status.
        </p>
      </Section>

      {/* Delhi Context */}
      <Section title="Delhi Electricity Demand Patterns" icon={Zap} delay={0.35}>
        <p>
          Delhi has some of the most extreme seasonal demand variation in the world:
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Season</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Months</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">Typical Demand</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Key Driver</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              <tr className="border-b border-border/50">
                <td className="p-2.5 font-medium">Winter</td>
                <td className="p-2.5">Nov - Feb</td>
                <td className="p-2.5 text-center font-mono">2,500 - 4,000 MW</td>
                <td className="p-2.5">Low demand, minimal heating</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5 font-medium">Spring</td>
                <td className="p-2.5">Mar - Apr</td>
                <td className="p-2.5 text-center font-mono">3,500 - 5,500 MW</td>
                <td className="p-2.5">Rapidly rising, AC usage begins</td>
              </tr>
              <tr className="border-b border-border/50 bg-amber-500/5">
                <td className="p-2.5 font-medium text-amber-400">Summer</td>
                <td className="p-2.5">May - Jun</td>
                <td className="p-2.5 text-center font-mono text-amber-400">5,000 - 8,500+ MW</td>
                <td className="p-2.5">Peak demand! AC dominates (45-48C)</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5 font-medium">Monsoon</td>
                <td className="p-2.5">Jul - Sep</td>
                <td className="p-2.5 text-center font-mono">4,500 - 7,000 MW</td>
                <td className="p-2.5">High humidity drives AC even at lower temps</td>
              </tr>
              <tr className="border-b border-border/50">
                <td className="p-2.5 font-medium">Autumn</td>
                <td className="p-2.5">Oct</td>
                <td className="p-2.5 text-center font-mono">3,000 - 4,500 MW</td>
                <td className="p-2.5">Transitional, AQI worsens (stubble burning)</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-xs">
          The summer peak (8,500+ MW) is more than <strong className="text-foreground">3x the winter minimum</strong> (2,500 MW).
          This extreme variation is driven almost entirely by air conditioning.
          Delhi generates almost no power locally — all electricity is purchased from generators across Northern India.
        </p>
      </Section>

      {/* Sub-Regional / DISCOM Forecasting */}
      <Section title="Sub-Regional (DISCOM) Forecasting" icon={Zap} delay={0.38}>
        <p>
          Delhi&#39;s electricity is distributed by <strong className="text-foreground">5 DISCOMs</strong> (distribution companies).
          Gridalytics forecasts demand for each sub-region by applying <strong className="text-foreground">historical demand ratios</strong> to
          the total Delhi forecast.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-border">
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">DISCOM</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Full Name</th>
                <th className="text-left p-2.5 text-xs font-medium text-muted-foreground">Area</th>
                <th className="text-center p-2.5 text-xs font-medium text-muted-foreground">Approx Share</th>
              </tr>
            </thead>
            <tbody className="text-xs">
              {[
                { code: "BRPL", name: "BSES Rajdhani Power Ltd", area: "South & West Delhi", share: "~35%" },
                { code: "NDPL/TPDDL", name: "Tata Power Delhi Distribution Ltd", area: "North & Northwest", share: "~25%" },
                { code: "BYPL", name: "BSES Yamuna Power Ltd", area: "Central & East Delhi", share: "~20%" },
                { code: "NDMC", name: "New Delhi Municipal Council", area: "Lutyens&#39; Delhi (New Delhi)", share: "~10%" },
                { code: "MES", name: "Military Engineering Services", area: "Delhi Cantonment", share: "~5%" },
              ].map((d) => (
                <tr key={d.code} className="border-b border-border/50">
                  <td className="p-2.5 font-mono font-bold text-foreground">{d.code}</td>
                  <td className="p-2.5">{d.name}</td>
                  <td className="p-2.5">{d.area}</td>
                  <td className="p-2.5 text-center font-mono">{d.share}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs">
          The ratios are computed dynamically from the last 30 days of actual SCADA data. You can see
          the DISCOM breakdown on the <strong className="text-foreground">Dashboard</strong> (horizontal bar chart)
          and request per-region forecasts via the API.
        </p>
      </Section>

      {/* What-If Scenarios */}
      <Section title="What-If Scenario Testing" icon={FlaskConical} delay={0.41}>
        <p>
          The <strong className="text-foreground">What-If</strong> page lets you override weather and event conditions
          to explore their impact on demand. This is useful for:
        </p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li><strong className="text-foreground">Grid capacity planning</strong> — &#34;What if we get a 48&#176;C heatwave next week?&#34;</li>
          <li><strong className="text-foreground">Emergency preparedness</strong> — &#34;How much extra power do we need for Diwali?&#34;</li>
          <li><strong className="text-foreground">Pollution impact</strong> — &#34;If AQI hits 500 (hazardous), how does demand change?&#34;</li>
          <li><strong className="text-foreground">Sensitivity analysis</strong> — &#34;How much does each &#176;C increase add to demand?&#34;</li>
        </ul>
        <div className="rounded-lg bg-accent/30 p-4 border border-border mt-3">
          <p className="text-xs font-medium text-foreground mb-2">Available parameters (7 total):</p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {[
              { param: "Temperature", range: "5-50&#176;C", effect: "Primary driver (AC load)" },
              { param: "Humidity", range: "10-100%", effect: "Feels-like temperature" },
              { param: "AQI", range: "0-500", effect: "Indoor activity shift" },
              { param: "Cloud Cover", range: "0-100%", effect: "Solar/AC patterns" },
              { param: "Holiday", range: "On/Off", effect: "Office closures" },
              { param: "Festival", range: "6 types", effect: "Diwali, IPL, etc." },
              { param: "Resolution", range: "5min/hr/day", effect: "Granularity level" },
            ].map((p) => (
              <div key={p.param} className="rounded bg-background/50 p-2">
                <p className="font-medium text-foreground">{p.param}</p>
                <p className="text-muted-foreground">{p.range}</p>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs mt-2">
          <strong className="text-foreground">How to interpret results:</strong> The blue line shows the baseline forecast
          (using actual/predicted conditions). The orange line shows your scenario. A positive percentage change means
          the scenario <em>increases</em> demand — the grid needs more power. A negative change means lower demand.
          Both average and peak impacts are shown separately because peak capacity is the critical safety constraint.
        </p>
      </Section>

      {/* Model Selection */}
      <Section title="Choosing a Model" icon={Brain} delay={0.44}>
        <p>
          On the <strong className="text-foreground">Forecast</strong> page, you can select which model to use
          via the Model dropdown:
        </p>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li><strong className="text-foreground">Auto (Best)</strong> — Uses the champion model for the selected resolution. Recommended for most use cases.</li>
          <li><strong className="text-foreground">LightGBM</strong> — Gradient boosting. Fastest, best for 5-minute. Optuna-tuned version available for hourly.</li>
          <li><strong className="text-foreground">XGBoost</strong> — Gradient boosting. Champion for hourly resolution.</li>
          <li><strong className="text-foreground">Ensemble</strong> — Weighted average of all loaded models. Can be more stable but not always most accurate.</li>
          <li><strong className="text-foreground">LSTM / BiLSTM</strong> — Deep learning. Captures sequence patterns but less accurate than tree models on this data.</li>
        </ul>
        <p className="text-xs mt-2">
          For most users, <strong className="text-foreground">Auto</strong> is the best choice. It automatically selects
          the champion model for each resolution (LightGBM for 5-min and daily, XGBoost for hourly).
        </p>
      </Section>

      {/* External Links */}
      <motion.div {...fadeIn(0.4)} className="flex flex-wrap gap-3 pt-2">
        {[
          { label: "Delhi SLDC", url: "https://www.delhisldc.org/" },
          { label: "Load Data", url: "https://www.delhisldc.org/Loaddata.aspx" },
          { label: "Open-Meteo", url: "https://open-meteo.com/" },
          { label: "API Docs", url: "http://localhost:8000/docs" },
        ].map((link) => (
          <a
            key={link.label}
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border border-border text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            {link.label}
          </a>
        ))}
      </motion.div>
    </div>
  );
}
