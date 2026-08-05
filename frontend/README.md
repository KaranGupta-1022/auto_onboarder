# GhostKube Console

The Phase 12 frontend: an operator console for the GhostKube Brain API. Next.js App Router,
TypeScript, plain CSS modules with the locked design tokens as custom properties — no Tailwind.

## Run locally

The Brain API must be running first — see [`../api/README.md`](../api/README.md). By default this
app talks to `http://localhost:8000`.

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). It redirects to `/ingest`.

## Configuration

`NEXT_PUBLIC_API_URL` sets the Brain API base URL — create `.env.local` to override the
`http://localhost:8000` default:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Pages

| Route | Purpose |
| ----- | ------- |
| `/ingest` | Submit a URL to `POST /ingest`; recent jobs (chunks/characters/status) persist to `sessionStorage` for the session |
| `/explorer` | Search `POST /ghost-note`; ranked result cards with relevance pills, 👍/👎 feedback |
| `/cluster` | `GET /pods` — pods labeled `ghostkube.io/service` and their webhook-injection status |
| `/notes/[chunkId]` | Full chunk + metadata. Reached by clicking an Explorer result (carries the relevance score and query via `sessionStorage`), or directly by URL (falls back to `GET /chunk/{id}` — full text, no relevance score, since there's no query to score against) |

## Structure

- `src/lib/api.ts` — typed client for every Brain API call, with centralized `ApiError` handling
- `src/lib/relevance.ts` — the relevance pill color-band thresholds, shared by Explorer and Note
  Detail so they can't drift out of sync
- `src/app/layout.tsx` + `src/app/Sidebar.tsx` — shell and nav (`Sidebar` is a client component for
  `usePathname()`-based active-link highlighting; kept separate so the root layout can stay a
  server component and still export `metadata`)
- `src/app/globals.css` — the locked design tokens as CSS custom properties (colors, fonts,
  sidebar/content widths)
- Each route owns its `page.tsx`, `page.module.css`, and (where needed) a small local `icons.tsx`
  of inline SVGs — no icon package dependency

## Notes on the design

Built against `design/*.png`, with a few deliberate deviations from those Canva mocks where the
Brain API doesn't have the data to back them: no pod status/phase stats on Cluster (API only
returns injection status, not `Running`/`Pending`/`Failed`), no title field on Note Detail (chunks
don't have titles — the file/PR path is shown instead), and the Explorer relevance-pill thresholds
are recalibrated (52/40, not a generic 80/50) to `relevance_score`'s actual L2-distance-based
distribution — see `GhostKube_Guide.md`'s Phase 10 section for the survey data behind that.
