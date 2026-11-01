# Frontend (React + Vite + Tailwind)

Needs Node 20+. Run from this folder (PowerShell or Git Bash):

```
npm install
npm run dev        # http://localhost:5173, /api is proxied to http://localhost:8000
npm test           # unit test (number/date formatters)
npm run build      # type-check + production build
```

Start the backend first (see the root README). Optional `frontend/.env.local`:

- `VITE_BACKEND_URL`: proxy target if the backend isn't on port 8000
- `VITE_API_BASE_URL`: API base the browser calls (default `/api`)

All backend calls go through `src/api/client.ts`.
