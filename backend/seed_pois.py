"""One-off seed: load data/delhi_pois.csv into the pois table. Run from the backend root:
    python seed_pois.py
Safe to re-run (skips rows whose city+name already exists)."""
import csv
import json
from pathlib import Path

from sqlalchemy import select

from app.database.connection import SessionLocal
from app.database.models import POI


def to_bool(v, default=False):
    return default if v is None or str(v).strip() == "" else str(v).strip().lower() in {"1", "true", "yes", "y"}


def to_float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def main():
    path = Path(__file__).parent / "data" / "delhi_pois.csv"
    added = skipped = 0
    with SessionLocal() as db, open(path, encoding="utf-8-sig", newline="") as f:
        # Many CSV rows have no osm_id, so de-duplicate on (city, name) instead.
        existing = {(c.lower(), n.lower()) for c, n in db.execute(select(POI.city, POI.name)).all()}
        osm_ids = set(db.scalars(select(POI.osm_id).where(POI.osm_id.is_not(None))))
        for r in csv.DictReader(f):
            osm_id = (r.get("osm_id") or "").strip()
            if osm_id.endswith(".0"):
                osm_id = osm_id[:-2]
            name = (r.get("name") or "").strip()
            lat, lon = to_float(r.get("lat")), to_float(r.get("lon"))
            city = (r.get("city") or "Delhi").strip()
            key = (city.lower(), name.lower())
            if not name or lat is None or lon is None or key in existing or osm_id in osm_ids:
                skipped += 1
                continue
            try:
                tags = json.loads(r.get("tags") or "[]")
            except json.JSONDecodeError:
                tags = []
            visit = to_float(r.get("visit_minutes"))
            db.add(POI(
                osm_id=osm_id or None,
                source_provider="curated",
                city=city,
                name=name,
                category=(r.get("category") or "attraction").strip().lower(),
                lat=lat, lon=lon,
                opening_hours=r.get("opening_hours") or None,
                est_cost=to_float(r.get("est_cost")),
                visit_minutes=int(visit) if visit and visit > 0 else None,
                popularity_score=to_float(r.get("popularity_score"), 0.0),
                tags={"tags": tags},
                hours_estimated=to_bool(r.get("hours_estimated"), True),
                cost_estimated=to_bool(r.get("cost_estimated"), True),
                website=r.get("website") or None,
                wikipedia=r.get("wikipedia") or None,
                description=r.get("description") or None,
            ))
            existing.add(key)
            if osm_id:
                osm_ids.add(osm_id)
            added += 1
        db.commit()
    print(f"Inserted {added} POIs, skipped {skipped}.")


if __name__ == "__main__":
    main()
