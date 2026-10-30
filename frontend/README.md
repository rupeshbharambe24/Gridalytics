# Gridalytics Frontend

Next.js 14 (app-router) dashboard for Gridalytics — electricity-demand forecasting across
**India's state power grids**. Includes a state-wise coverage view (`/states`: 36-state map,
per-state status, demand & analysis) alongside the Delhi forecast/analytics views.
Built with Tailwind CSS, Recharts, Framer Motion, and shadcn/ui.

## Develop

```bash
npm install
npm run dev     # http://localhost:3000
npm run build   # production build
npm run lint
```

The API base URL comes from `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`):

```bash
# .env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Structure

- `src/app/(dashboard)/*` — dashboard pages: overview, forecast, analytics, accuracy,
  models, what-if, admin, info (plus `layout.tsx` with the sidebar shell).
- `src/lib/api.ts` — typed API client (reads `NEXT_PUBLIC_API_URL`).
- `src/lib/hooks.ts` — `useFetch`, with a **shared stale-while-revalidate cache** so
  revisiting a tab shows data instantly and revalidates in the background, and identical
  requests are de-duplicated across tabs.
- `src/components/` — charts (Recharts), dashboard KPI cards, layout, and UI primitives.

## Performance

Data is cached per endpoint across tabs and revalidated in the background, so navigating
between tabs doesn't re-fetch from scratch or flash skeletons. See
[`../docs/frontend_performance.md`](../docs/frontend_performance.md) for the full
diagnosis and recommended follow-ups (code-split charts via `next/dynamic`, server-render
the first paint, or add an aggregate `/dashboard/overview` endpoint).
