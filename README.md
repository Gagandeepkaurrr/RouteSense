# RouteSense

React + Vite frontend in `frontend/`, connected to the supplied FastAPI backend in `backend/`. The original page layout, styles, navigation and MapLibre map are retained.

## Run locally

Backend dependencies have been installed in `backend/.venv` using the installed Python 3.13 interpreter. Python 3.11 is recommended by the handoff, but its downloaded interpreter was blocked by Windows Application Control here.

The backend ZIP included a private `.env`; it is retained only in `backend/` and ignored by Git. Review its database, Geoapify and cookie settings locally. No secrets are copied into frontend code.

In a terminal:

```powershell
cd C:\Users\sukhm\RouteSense\backend
docker compose up -d
# With PostgreSQL running and DATABASE_URL configured:
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe seed_pois.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The seed command loads the bundled Delhi catalog into PostgreSQL and skips existing places on reruns. For road lines on the map, follow the [OSRM setup](backend/README.md).

In another terminal:

```powershell
cd C:\Users\sukhm\RouteSense\frontend
npm install
npm run dev
```

Open the URL printed by Vite. The default API base `/backend-api` is proxied to `http://127.0.0.1:8000`. This keeps browser requests and cookies on the frontend host during local development. Optional configuration is in `frontend/.env.example`. For production, provide an equivalent reverse proxy or set `VITE_API_BASE_URL` to the API origin before building and configure backend CORS and cookie settings for that deployment. Vite's development proxy is not part of the production build.

## Vercel frontend deployment

Import the repository with Root Directory set to the repository root (`.`). The root `vercel.json` installs and builds `frontend/`, serves `frontend/dist`, and supports direct navigation to frontend pages.

Set `VITE_API_BASE_URL` in Vercel to your deployed backend's HTTPS origin before building. The local `/backend-api` proxy only works with the Vite development server. Host FastAPI, PostgreSQL and OSRM separately; this configuration deploys only the frontend. Configure backend `CORS_ORIGINS` for the Vercel frontend origin and appropriate HTTPS cookie settings (`COOKIE_SECURE=true`, and `COOKIE_SAMESITE=none` for cross-site deployment). Redeploy after changing Vite environment variables.

## Features connected

- Signup, login, session restoration and logout use `/api/auth/signup`, `/login`, `/me`, `/logout`.
- The trip form first calls `POST /api/v1/itineraries/extract`, displays the backend's clarification questions or extracted summary, then calls `POST /api/v1/itineraries/generate` after confirmation. Both calls handle HTTP 200 clarification responses.
- Profile loads `GET /api/v1/itineraries`; open and delete use `GET` and `DELETE /api/v1/itineraries/{trip_id}`. Empty HTTP 204 responses are supported.
- All requests use `credentials: include`. Protected-request 401 clears the current user and itinerary and displays sign-in. Login 401 stays on the form; initial `/me` 401 means signed out. JWTs are never stored in browser storage.
- Days and stops remain in backend order. MapLibre receives `[longitude, latitude]` markers and returned GeoJSON road geometry. Initial selection is A-to-B; selecting a stop selects its incoming leg without making any API request. Null geometry is labelled unavailable and is not replaced by a straight road line.
- ETAs, day and trip totals, schedules in Asia/Kolkata, estimated costs/hours/visit durations, warnings, budget warnings, unscheduled places, weather fallbacks and ETA fallbacks use backend fields.
- Local stop removal was removed because the supplied backend has no endpoint to recalculate or persist that edit.

## Verification and current blockers

See `INTEGRATION_REPORT.md` for results and changed files. Build, lint and six API-client tests passed. Browser checks using a temporary API fixture passed for clarification, generation, map geometry, leg selection, day switching, saved-list and saved-detail rendering. These are frontend checks, not live backend acceptance tests.

Live FastAPI startup failed because Windows Application Control blocked SQLAlchemy's `_collections_cy` compiled module. Docker was not available on PATH, and no service was listening on ports 5432 or 5000 when checked. Live authentication, PostgreSQL persistence, POI generation, OSRM, weather and ML behavior remain untested. No backend source or security policy was changed to work around these machine setup blockers.

```powershell
cd C:\Users\sukhm\RouteSense\frontend
npm test
npm run lint
npm run build
```
