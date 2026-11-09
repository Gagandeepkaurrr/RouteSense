# Integration report

## Changed frontend files

- `frontend/src/api.js` (new): central configured cookie API client, errors, request IDs and 204 handling.
- `frontend/src/App.jsx`: session restoration, protected screens, current trip state and logout.
- `frontend/src/pages/auth.jsx`: real signup/login, pending state and errors.
- `frontend/src/pages/home.jsx`: parser-compatible filters and Delhi prompt.
- `frontend/src/pages/plan_trip.jsx`: extraction, clarification, confirmation, generation, backend itinerary fields and GeoJSON map.
- `frontend/src/pages/plan_trip.css`: minimal form and response styles.
- `frontend/src/pages/profile.jsx`: real user, saved list, details, delete, logout and available summary fields.
- `frontend/vite.config.js`: local API proxy.
- `frontend/.env.example` (new): public API configuration example.
- `frontend/package.json`: Node test command.
- `frontend/tests/api.test.mjs` (new): six API-client tests.

Other changes: root `.gitignore` excludes private environments and Python dependencies; root README and the pre-existing backend placeholder README now describe actual startup. Backend archive files were added under `backend/`; source, configuration, model and routing data were preserved. A local ignored `backend/.venv` was installed for startup verification.

## Tests actually run

| Check | Result | Evidence / limit |
|---|---|---|
| Production frontend build | PASS | `npm run build`; MapLibre bundle size warning only |
| Frontend lint | PASS | `npm run lint` |
| API-client suite | PASS | Six Node tests: signup contract/credentials, HTTP 200 clarification for extract/generate, empty delete 204, protected 401 versus login 401, validation/request ID, network/non-JSON errors |
| Backend archive integrity | PASS | Sizes and CRC32 matched all 109 files, including processed OSRM data |
| Browser clarification and ready summary | PASS with fixture | Entered `Delhi`, displayed backend question, answered `2`, confirmed prompt became `Delhi, 2 days` |
| Browser itinerary and map | PASS with fixture | Generated two days; road GeoJSON and ordered A/B/C markers rendered; costs, warning and unscheduled place displayed |
| Initial and selected leg | PASS with fixture | Initially A-to-B ML ETA; selected C changed to B-to-C fallback ETA and null-road label |
| No generation on stop/day selection | PASS with fixture | Temporary server log contained one generate call across selection and day switch |
| Day isolation | PASS with fixture | Day 2 showed only Red Fort and no incoming leg |
| Saved list/detail | PASS with fixture | Profile listed trip and Open fetched `/api/v1/itineraries/42` and rendered snapshot |
| Real FastAPI startup | FAIL: environment | Windows Application Control blocked SQLAlchemy `_collections_cy` DLL load, before server startup |
| Live health, extraction, protected generate, DB readiness | NOT TESTED | Requests attempted against port 8000 while FastAPI was stopped; connection errors, no HTTP response/request ID |
| Live signup/login/logout/cookie/session restoration | NOT TESTED | FastAPI unavailable; no PostgreSQL service detected |
| Live saved list/detail/delete persistence | NOT TESTED | FastAPI/PostgreSQL unavailable; delete 204 covered at client level only |
| Live OSRM/weather/ML and POI generation | NOT TESTED | Docker unavailable and no OSRM service detected |
| Production CORS/cookie deployment | NOT TESTED | Local proxy configured; deployed origins not supplied |

The temporary fixture server was stopped after browser checks and is not included in the application. It did not write any backend/database data. Browser checks do not establish that authentication cookies or real backend generation work.

## Behavior and endpoint details

See the root README's feature list for endpoint mapping, cookies, 401 handling, map geometry, leg selection and fallback labels. Frontend has no direct calls to Geoapify, OSRM or Open-Meteo. Public map tiles remain the existing OpenFreeMap style. No new dependency or UI framework was added to the frontend.

Current blockers are local execution policy, Docker/OSRM and PostgreSQL readiness. Database credentials and curated POI availability have not been validated. No service or security-policy changes were made, and no migrations or database seed operations were run.
