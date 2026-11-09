"""Repository helpers for loading the curated Delhi POI database."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import POI as POIModel
from .hours import parse_hours
from .pois import POI


def load_curated_pois(db: Session, city: str = "Delhi") -> list[POI]:
    records = db.scalars(
        select(POIModel).where(POIModel.city.ilike(city))
    ).all()

    result: list[POI] = []
    for record in records:
        raw_tags = record.tags or {}
        if isinstance(raw_tags, dict):
            tag_values = raw_tags.get("tags", [])
        elif isinstance(raw_tags, list):
            tag_values = raw_tags
        else:
            tag_values = []

        result.append(
            POI(
                id=(
                    str(record.osm_id)
                    if record.osm_id is not None
                    else f"db_poi_{record.id}"
                ),
                name=record.name,
                category=record.category.lower(),
                lat=record.lat,
                lon=record.lon,
                cost=record.est_cost or 0.0,
                duration=max(15, min(360, record.visit_minutes or 60)),
                popularity=max(0.0, min(5.0, record.popularity_score or 0.0)),
                tags={
                    str(tag).lower()
                    for tag in tag_values
                    if isinstance(tag, str)
                },
                hours_raw=record.opening_hours or "",
                hours=parse_hours(record.opening_hours),
                description=record.description or "",
                extra={
                    "database_id": record.id,
                    "source": "curated",
                    "sources": ["curated"],
                    "score_method": "curated_popularity",
                    "base_score": float(record.popularity_score or 0.0),
                    "hours_estimated": record.hours_estimated,
                    "cost_estimated": record.cost_estimated,
                    "visit_duration_estimated": True,
                    "website": record.website or "",
                    "wikipedia": record.wikipedia or "",
                    "source_provider": record.source_provider,
                    "provider_id": record.provider_id,
                },
            )
        )
    return result
