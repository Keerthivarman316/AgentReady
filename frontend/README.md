# AgentReady frontend

Next.js (App Router, TypeScript, Tailwind) — three surfaces over the backend API.

## Setup

```
npm install
copy .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if the backend isn't on :8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The backend (`../backend`) must be
running with a seeded database for anything beyond the landing page to load real data.

## Surfaces

- **`/buyer`** — issue an AP2 mandate from a natural-language goal, preview the 3-layer
  ranking live as you move the weight sliders (`POST /buyer/rank-preview`, no checkout
  side effect), then confirm purchase (`POST /buyer/purchase`) to see checkout succeed
  or fall back to the next-ranked merchant.
- **`/merchant` → `/merchant/[id]`** — Trust Mirror, category Benchmark, Growth Advisor
  fix list with a what-if re-ranking simulator, SLA Advisor, and a Readiness Agent
  catalog checker, all re-fetched live as the weight sliders move.
- **`/audit`** — full audit trail for a mandate, in order, color-coded for checkout
  failures/fallbacks.

## Verify

```
npm run lint
npm run build
```
