# RouteSense backend

This directory contains the FastAPI backend, migrations, travel-time model and curated Delhi place catalog. OSRM routing data is prepared locally and excluded from Git.

See `../README.md` for startup instructions and `../INTEGRATION_REPORT.md` for verification and machine setup blockers. Entry point: `app.main:app`, port 8000. OSRM setup is below. Configure PostgreSQL and apply the existing migrations before using authenticated persistence. Curated POI data is required for itinerary generation.

From this directory, run `alembic upgrade head` followed by `python seed_pois.py` with the backend environment active to load the bundled Delhi catalog. Rerunning the seed skips existing places.

To enable road lines locally, download the [Northern Zone OpenStreetMap extract](https://download.geofabrik.de/asia/india/northern-zone.html) as `osrm-data/northern-zone-latest.osm.pbf`. From the backend directory, crop the extract to Delhi and nearby areas with Osmium, then prepare the graph:

```sh
osmium extract --strategy=complete_ways --bbox=76.75,28.3,77.6,29.05 \
  osrm-data/northern-zone-latest.osm.pbf -o osrm-data/delhi.osm.pbf
image=ghcr.io/project-osrm/osrm-backend:latest
docker run --rm -v "$PWD/osrm-data:/data" "$image" osrm-extract -p /opt/car.lua /data/delhi.osm.pbf
docker run --rm -v "$PWD/osrm-data:/data" "$image" osrm-partition /data/delhi.osrm
docker run --rm -v "$PWD/osrm-data:/data" "$image" osrm-customize /data/delhi.osrm
docker compose up -d osrm
curl -f 'http://localhost:5001/route/v1/driving/77.2090,28.6139;77.2167,28.6304?overview=full&geometries=geojson'
```

Set `OSRM_URL=http://127.0.0.1:5001` in the backend `.env`, restart FastAPI, and generate a new itinerary. Saved trips retain their original route data.
