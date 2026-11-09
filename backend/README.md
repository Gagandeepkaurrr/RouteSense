# RouteSense backend

The supplied backend package is extracted directly into this directory, including its model, private `.env`, migrations and processed `osrm-data`. All 109 archive files were verified against ZIP sizes and CRCs without modification. This README replaces the old frontend placeholder and was not part of the ZIP.

See `../README.md` for startup instructions and `../INTEGRATION_REPORT.md` for verification and machine setup blockers. Entry point: `app.main:app`, port 8000. OSRM: `docker compose up -d`, port 5000. Configure PostgreSQL and apply the existing migrations before using authenticated persistence. Curated POI data is required for itinerary generation.
