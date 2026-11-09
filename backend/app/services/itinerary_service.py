"""End-to-end itinerary generation and persistence orchestration."""
from __future__ import annotations

import logging
from datetime import date as Date, datetime, time as Time
from functools import lru_cache
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import (
    ItineraryDay,
    ItineraryStop,
    POI as POIModel,
    Trip,
    User,
)
from app.schemas.intake import TripExtractionRequest
from app.schemas.itinerary import (
    GeneratedItineraryResponse,
    InsufficientPoolResponse,
)
from app.services.intake_service import extract_trip_prompt
from app.services.planner import TripRequest, plan_trip
from app.services.planner.geoapify import get_geoapify_candidate_pois
from app.services.planner.pois import POI
from app.services.planner.repository import load_curated_pois
from app.services.planner.routing import OsrmClient, add_routes
from app.services.planner.travel import HeuristicTravel

logger = logging.getLogger(__name__)
DELHI_TZ = ZoneInfo("Asia/Kolkata")
MIN_PLACES_PER_DAY = 2


@lru_cache(maxsize=1)
def _osrm_client() -> OsrmClient | None:
    url = settings.OSRM_URL.strip()
    return OsrmClient(url) if url else None


def _local_datetime(day: Date, hhmm: str) -> datetime:
    return datetime.combine(day, Time.fromisoformat(hhmm)).replace(tzinfo=DELHI_TZ)


def _poi_source(poi: POI) -> str:
    sources = poi.extra.get("sources", [])
    if "geoapify" in sources and "curated" not in sources:
        return "geoapify"
    if "geoapify" in sources and "curated" in sources:
        return "hybrid"
    return "curated"


def _resolve_poi_record(db: Session, poi: POI) -> POIModel:
    """Resolve curated POIs by their database ID; upsert live provider POIs."""
    database_id = poi.extra.get("database_id")
    if database_id is not None:
        existing = db.get(POIModel, int(database_id))
        if existing is not None:
            return existing

    source = _poi_source(poi)
    provider_id = poi.extra.get("provider_id")
    if source == "geoapify":
        provider_id = str(provider_id or poi.id)
        existing = db.scalar(
            select(POIModel).where(
                POIModel.source_provider == "geoapify",
                POIModel.provider_id == provider_id,
            )
        )
        if existing is not None:
            return existing
    else:
        existing = db.scalar(
            select(POIModel).where(POIModel.osm_id == poi.id)
        )
        if existing is not None:
            return existing

    record = POIModel(
        osm_id=None if source == "geoapify" or poi.id.startswith("db_poi_") else poi.id,
        source_provider=source if source == "geoapify" else "curated",
        provider_id=provider_id if source == "geoapify" else None,
        city="Delhi",
        name=poi.name,
        category=poi.category,
        lat=poi.lat,
        lon=poi.lon,
        opening_hours=poi.hours_raw or None,
        est_cost=poi.cost,
        visit_minutes=poi.duration,
        popularity_score=poi.popularity,
        tags={"tags": sorted(poi.tags)},
        hours_estimated=bool(poi.extra.get("hours_estimated", True)),
        website=poi.extra.get("website") or None,
        wikipedia=poi.extra.get("wikipedia") or None,
        description=poi.description or None,
        cost_estimated=bool(poi.extra.get("cost_estimated", True)),
    )
    db.add(record)
    db.flush()
    return record


def _build_response(
    trip_id: int,
    extracted,
    plan: dict,
) -> GeneratedItineraryResponse:
    travellers = extracted.number_of_travellers
    start_date = extracted.start_date
    days_payload = []
    total_stops = 0
    total_travel_minutes = 0

    for day in plan.get("days", []):
        day_date = Date.fromisoformat(day["date"])
        stops_payload = []
        stop_ids: list[str] = []

        for index, stop in enumerate(day.get("stops", []), start=1):
            stop_id = f"{trip_id}-d{day['day']}-s{index}"
            stop_ids.append(stop_id)
            total_stops += 1
            group_cost = float(stop.get("cost_inr") or 0)
            route = stop.get("route") or {}
            actual_arrival = stop.get("actual_arrival")
            stops_payload.append({
                "stop_id": stop_id,
                "poi_id": str(stop["id"]),
                "name": stop["name"],
                "coordinates": {
                    "latitude": float(stop["lat"]),
                    "longitude": float(stop["lon"]),
                },
                "category": stop["category"],
                "score": float(stop.get("score", 0)),
                "base_score": float(stop.get("base_score", stop.get("score", 0))),
                "score_method": stop.get("score_method", "curated_popularity"),
                "source": stop.get("source", "curated"),
                "sources": stop.get("sources", []),
                "matched_preferences": stop.get("matched_preferences", []),
                "scheduled_arrival": _local_datetime(day_date, stop["arrive"]),
                "scheduled_departure": _local_datetime(day_date, stop["leave"]),
                "actual_arrival": (
                    _local_datetime(day_date, actual_arrival)
                    if actual_arrival else None
                ),
                "visit_duration_minutes": int(stop.get("visit_minutes") or 60),
                "estimated_cost_per_person_inr": round(group_cost / travellers, 2),
                "estimated_cost_group_inr": round(group_cost, 2),
                "opening_hours": stop.get("opening_hours"),
                "opening_hours_estimated": bool(stop.get("opening_hours_estimated", True)),
                "cost_estimated": bool(stop.get("cost_estimated", True)),
                "visit_duration_estimated": bool(stop.get("visit_duration_estimated", True)),
                "schedule_conflict": bool(stop.get("schedule_conflict", False)),
            })

        legs_payload = []
        for index, stop in enumerate(day.get("stops", [])[1:], start=1):
            route = stop.get("route") or {}
            previous_stop_id = stop_ids[index - 1]
            current_stop_id = stop_ids[index]
            departure = route.get("depart") or day["stops"][index - 1]["leave"]
            weather = route.get("weather") or {
                "condition_used": "Clear",
                "source": "fallback",
                "forecast_available": False,
                "fallback_used": True,
                "fallback_reason": "weather_metadata_unavailable",
            }
            geometry = route.get("geometry")
            legs_payload.append({
                "leg_number": index,
                "from_stop_id": previous_stop_id,
                "to_stop_id": current_stop_id,
                "departure_time": _local_datetime(day_date, departure),
                "distance_km": float(route.get("distance_km") or 0),
                "distance_source": route.get("distance_source", "osrm" if geometry else "heuristic_estimate"),
                "osrm_duration_minutes": route.get("osrm_duration_min"),
                "predicted_duration_minutes": int(route.get("eta_min") or 0),
                "prediction_source": route.get("prediction_source", "unavailable"),
                "geometry": geometry,
                "weather": weather,
            })

        day_travel_minutes = int(day.get("route_eta_total_min") or 0)
        total_travel_minutes += day_travel_minutes
        days_payload.append({
            "day_number": int(day["day"]),
            "date": day_date,
            "origin_stop_id": stop_ids[0] if stop_ids else "",
            "stops": stops_payload,
            "legs": legs_payload,
            "total_distance_km": float(day.get("travel_km") or 0),
            "total_travel_minutes": day_travel_minutes,
            "estimated_cost_group_inr": float(day.get("spend_inr") or 0),
            "schedule_conflicts": sum(
                1 for stop in day.get("stops", [])
                if stop.get("schedule_conflict")
            ),
        })

    estimated_group = float(plan["summary"]["total_spend_inr"])
    estimated_per_person = estimated_group / travellers
    remaining_per_person = extracted.budget_per_person_inr - estimated_per_person

    return GeneratedItineraryResponse.model_validate({
        "status": "generated",
        "trip_id": trip_id,
        "trip": {
            "city": "Delhi",
            "start_date": start_date,
            "number_of_days": extracted.days,
            "budget_per_person_inr": extracted.budget_per_person_inr,
            "total_group_budget_inr": extracted.total_group_budget_inr,
            "number_of_travellers": travellers,
            "timezone": "Asia/Kolkata",
            "preferences": extracted.preferences,
            "pace": extracted.pace,
        },
        "summary": {
            "estimated_cost_per_person_inr": round(estimated_per_person, 2),
            "estimated_cost_group_inr": round(estimated_group, 2),
            "budget_remaining_per_person_inr": round(remaining_per_person, 2),
            "within_budget": remaining_per_person >= -0.01,
            "total_distance_km": float(plan["summary"]["total_travel_km"]),
            "total_travel_minutes": total_travel_minutes,
            "total_stops": total_stops,
        },
        "days": days_payload,
        "warnings": plan.get("warnings", []),
        "not_scheduled": plan.get("not_scheduled", []),
    })


def generate_and_save_itinerary(
    db: Session,
    user: User,
    request: TripExtractionRequest,
) -> GeneratedItineraryResponse | object:
    """Generate a Delhi itinerary, calculate its legs, and persist a snapshot."""
    extraction = extract_trip_prompt(request)
    if extraction.status == "needs_clarification":
        return extraction

    fields = extraction.extracted
    assert fields.days is not None

    curated = load_curated_pois(db, city="Delhi")
    candidates = get_geoapify_candidate_pois(
        interests=fields.preferences,
        base_pois=curated,
        limit_per_interest=6,
        radius_meters=12000,
    )

    required_places = max(fields.days, fields.days * MIN_PLACES_PER_DAY)
    sightseeing_count = sum(
        1 for poi in candidates
        if poi.category in {"attraction", "religious", "nature", "entertainment", "shopping"}
    )

    if len(candidates) < required_places or sightseeing_count < fields.days:
        expanded = get_geoapify_candidate_pois(
            interests=fields.preferences,
            base_pois=curated,
            limit_per_interest=12,
            radius_meters=20000,
        )
        if len(expanded) > len(candidates):
            candidates = expanded
        sightseeing_count = sum(
            1 for poi in candidates
            if poi.category in {"attraction", "religious", "nature", "entertainment", "shopping"}
        )

    if len(candidates) < required_places or sightseeing_count < fields.days:
        return InsufficientPoolResponse(
            status="needs_clarification",
            reason="insufficient_places",
            message=(
                "Not enough places with a score of at least 4 were found. "
                "Please broaden your interests or choose fewer days."
            ),
            available_places=len(candidates),
            required_places=required_places,
            extracted=fields.model_dump(mode="json"),
            missing_fields=["preferences"],
            questions=[{
                "field": "preferences",
                "question": "Would you like to add more interests such as parks, shopping, cafes or religious places?",
            }],
        )

    group_budget = fields.budget_per_person_inr * fields.number_of_travellers
    planner_request = TripRequest(
        days=fields.days,
        budget_total_inr=group_budget,
        interests=fields.preferences,
        start_date=fields.start_date,
        start_time=fields.start_time,
        pace=fields.pace,
        travellers=fields.number_of_travellers,
        start_location=None,
        city="Delhi",
    )

    plan = plan_trip(candidates, planner_request, travel=HeuristicTravel())
    add_routes(plan, start=None, osrm=_osrm_client())

    total_planned = sum(len(day.get("stops", [])) for day in plan.get("days", []))
    days_with_stops = sum(bool(day.get("stops")) for day in plan.get("days", []))
    if days_with_stops < fields.days or total_planned < fields.days:
        return InsufficientPoolResponse(
            status="needs_clarification",
            reason="insufficient_places",
            message=(
                "The available places could not produce a feasible stop for every day. "
                "Please broaden your interests or choose fewer days."
            ),
            available_places=len(candidates),
            required_places=required_places,
            extracted=fields.model_dump(mode="json"),
            missing_fields=["preferences"],
            questions=[{
                "field": "preferences",
                "question": "Would you like to broaden your preferences to include more categories?",
            }],
        )

    trip = Trip(
        user_id=user.id,
        destination="Delhi",
        start_date=fields.start_date,
        days=fields.days,
        budget=group_budget,
        preferences=fields.preferences,
        prompt=request.prompt,
        budget_per_person=fields.budget_per_person_inr,
        number_of_travellers=fields.number_of_travellers,
        pace=fields.pace,
        status="planned",
        warnings_json=plan.get("warnings", []),
        not_scheduled_json=plan.get("not_scheduled", []),
    )
    try:
        db.add(trip)
        db.flush()

        response = _build_response(trip.id, fields, plan)

        for day_data in plan.get("days", []):
            day_record = ItineraryDay(
                trip_id=trip.id,
                day_number=int(day_data["day"]),
                date=Date.fromisoformat(day_data["date"]),
                estimated_day_cost=float(day_data.get("spend_inr") or 0),
                total_distance_km=float(day_data.get("travel_km") or 0),
                total_travel_minutes=int(day_data.get("route_eta_total_min") or 0),
            )
            db.add(day_record)
            db.flush()

            for order, stop in enumerate(day_data.get("stops", []), start=1):
                poi_record = _resolve_poi_record(db, next(
                    poi for poi in candidates if poi.id == stop["id"]
                ))
                route = stop.get("route") or {}
                db.add(
                    ItineraryStop(
                        itinerary_day_id=day_record.id,
                        poi_id=poi_record.id,
                        stop_order=order,
                        planned_arrival=Time.fromisoformat(stop["arrive"]),
                        planned_departure=Time.fromisoformat(stop["leave"]),
                        visit_minutes=int(stop.get("visit_minutes") or 60),
                        estimated_travel_minutes=int(stop.get("travel_minutes_from_previous") or 0),
                        estimated_cost=float(stop.get("cost_inr") or 0),
                        score=float(stop.get("score") or 0),
                        base_score=float(stop.get("base_score") or stop.get("score") or 0),
                        score_method=stop.get("score_method"),
                        source=stop.get("source"),
                        sources_json=stop.get("sources", []),
                        matched_preferences_json=stop.get("matched_preferences", []),
                        route_json=route,
                        cost_estimated=bool(stop.get("cost_estimated", True)),
                        visit_duration_estimated=bool(stop.get("visit_duration_estimated", True)),
                        opening_hours_estimated=bool(stop.get("opening_hours_estimated", True)),
                        travel_time_estimated=True,
                    )
                )

        trip.itinerary_json = response.model_dump(mode="json")
        db.add(trip)
        db.commit()
        return response
    except Exception:
        db.rollback()
        logger.exception("Failed to persist generated itinerary for user %s", user.id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "ITINERARY_SAVE_FAILED",
                "message": "The itinerary could not be saved. Please try again.",
            },
        )


def list_saved_itineraries(db: Session, user: User) -> list[Trip]:
    return list(
        db.scalars(
            select(Trip)
            .where(Trip.user_id == user.id)
            .order_by(Trip.created_at.desc())
        ).all()
    )


def get_saved_itinerary(db: Session, user: User, trip_id: int) -> Trip:
    trip = db.scalar(
        select(Trip).where(Trip.id == trip_id, Trip.user_id == user.id)
    )
    if trip is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ITINERARY_NOT_FOUND",
                "message": "The requested itinerary was not found.",
            },
        )
    return trip


def delete_saved_itinerary(db: Session, user: User, trip_id: int) -> None:
    trip = get_saved_itinerary(db, user, trip_id)
    db.delete(trip)
    db.commit()
