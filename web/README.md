# AdPulse web app

The client-facing interface: React 19, Vite 7, TypeScript, Tailwind CSS 4, React Router, TanStack Query,
Recharts, Motion, and the Three.js robot (React Three Fiber). It talks only to the Python API in `../api`,
never to ClickHouse or the AI provider, so no secrets live in the browser.

## Develop

From the repository root:

```bash
make api              # API on http://localhost:8000
```

```bash
make web-install && make web    # http://localhost:5173
```

Vite forwards `/api` to `localhost:8000`, so `VITE_API_URL` stays empty in development.

## Build

```bash
npm run build         # type-check, then build into dist/
```

## Deploy (Vercel)

- Root Directory: `web` (build settings, routing and caching come from `vercel.json`).
- Environment variable: `VITE_API_URL` = the API's public address, e.g. `https://adpulse-api-production.up.railway.app`.

Full guide: [../docs/deploy-vercel-railway.md](../docs/deploy-vercel-railway.md).

## Structure

```
src/pages/        Overview, Ask, Suggestions, Wasted, Report, DataStatus, Present (client deck)
src/components/   Layout (header, footer), ui (shared parts), charts, KpiCard and Funnel (adapted from
                  21st.dev components, credited in each file), Brand logos, RobotLauncher, Logo (wordmark)
src/lib/          api client and response types, number and date formatting, reviewer name
src/robot/        3D robot scene and animation
public/           favicon, brand logos (svgl.app), robot.glb (CC0 placeholder model)
```
