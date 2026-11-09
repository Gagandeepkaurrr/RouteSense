"""OSRM routing and scheduled, weather-aware ML travel-time prediction."""
from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import date as Date, datetime, time as Time
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import joblib
import pandas as pd

from app.config import settings
from .hours import fit_visit, parse_hours
from .travel import HeuristicTravel, haversine_km

logger = logging.getLogger(__name__)
DELHI_TZ = ZoneInfo("Asia/Kolkata")
MAX_DISTANCE_FROM_DELHI_KM = 50.0

MODEL_PATH = (
    Path(__file__).resolve().parents[3]
    / "model"
    / "delhi_travel_time_model_v2.pkl"
)

try:
    TRAVEL_TIME_MODEL = joblib.load(MODEL_PATH)
except Exception:
    logger.exception("Could not load the RouteSense travel-time model")
    TRAVEL_TIME_MODEL = None


def predict_travel_time(
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    distance_km: float,
    depart_min: int,
    date: Date,
    weather_condition: str = "Clear",
) -> float:
    """Predict a leg's duration using the existing eight-feature pipeline."""
    if TRAVEL_TIME_MODEL is None:
        raise RuntimeError("The trained travel-time model is unavailable")

    hour = (depart_min // 60) % 24
    if 7 <= hour < 11:
        time_of_day = "Morning Peak"
    elif 11 <= hour < 16:
        time_of_day = "Afternoon"
    elif 16 <= hour < 20:
        time_of_day = "Evening Peak"
    else:
        time_of_day = "Night"

    features = pd.DataFrame([{
        "start_lat": float(start_lat),
        "start_lon": float(start_lon),
        "end_lat": float(end_lat),
        "end_lon": float(end_lon),
        "distance_km": float(distance_km),
        "time_of_day": time_of_day,
        "weather_condition": weather_condition,
        "day_of_week": "Weekend" if date.weekday() >= 5 else "Weekday",
    }])
    prediction = TRAVEL_TIME_MODEL.predict(features)[0]
    return max(1.0, float(prediction))


_weather_cache: dict[tuple, tuple[float, dict]] = {}
_weather_cache_lock = Lock()


def _weather_category(weather_code: int | None, temperature: float | None) -> str:
    if weather_code in (45, 48):
        return "Fog"
    if weather_code in (
        51, 53, 55, 56, 57, 61, 63, 65, 66, 67,
        80, 81, 82, 95, 96, 99,
    ):
        return "Rain"
    if temperature is not None and temperature >= 38:
        return "Heatwave"
    return "Clear"


def _weather_cache_key(lat: float, lon: float, depart_min: int, trip_date: Date) -> tuple:
    return (round(lat, 3), round(lon, 3), trip_date.isoformat(), (depart_min // 60) % 24)


def _weather_cache_get(key: tuple) -> dict | None:
    now = time.monotonic()
    with _weather_cache_lock:
        entry = _weather_cache.get(key)
        if entry is None:
            return None
        expiry, value = entry
        if expiry <= now:
            _weather_cache.pop(key, None)
            return None
        return dict(value)


def _weather_cache_set(key: tuple, value: dict) -> None:
    with _weather_cache_lock:
        now = time.monotonic()
        expired = [k for k, (expiry, _) in _weather_cache.items() if expiry <= now]
        for old_key in expired:
            _weather_cache.pop(old_key, None)
        while len(_weather_cache) >= 512:
            oldest = min(_weather_cache, key=lambda k: _weather_cache[k][0])
            _weather_cache.pop(oldest, None)
        _weather_cache[key] = (
            now + max(60, settings.WEATHER_CACHE_TTL_SECONDS),
            dict(value),
        )


def get_weather_details(
    lat: float,
    lon: float,
    depart_min: int,
    trip_date: Date,
) -> dict:
    """Return date/hour weather plus explicit forecast/fallback provenance.

    Open-Meteo's standard forecast horizon is bounded. Dates beyond the
    configured horizon use Clear only as a neutral model input and are
    explicitly marked as a fallback, never as an actual forecast.
    """
    now_date = datetime.now(DELHI_TZ).date()
    days_ahead = (trip_date - now_date).days
    max_days = max(0, settings.WEATHER_FORECAST_MAX_DAYS)

    if days_ahead < 0:
        return {
            "condition_used": "Clear",
            "source": "fallback",
            "forecast_available": False,
            "fallback_used": True,
            "fallback_reason": "date_outside_forecast_range",
        }
    if days_ahead > max_days:
        return {
            "condition_used": "Clear",
            "source": "fallback",
            "forecast_available": False,
            "fallback_used": True,
            "fallback_reason": "date_outside_forecast_range",
        }

    key = _weather_cache_key(lat, lon, depart_min, trip_date)
    cached = _weather_cache_get(key)
    if cached is not None:
        cached["cache_hit"] = True
        return cached

    hour = (depart_min // 60) % 24
    target_time = datetime.combine(trip_date, Time(hour=hour))
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weather_code",
        "start_date": trip_date.isoformat(),
        "end_date": trip_date.isoformat(),
        "timezone": "Asia/Kolkata",
    }

    try:
        import httpx

        last_error = None
        payload = None
        for attempt in range(3):
            response = httpx.get(
                settings.OPEN_METEO_BASE_URL,
                params=params,
                timeout=8.0,
            )
            if response.status_code == 429 or response.status_code in {500, 502, 503, 504}:
                if attempt == 2:
                    response.raise_for_status()
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(2.0, max(0.0, float(retry_after))) if retry_after else 0.5 * (2 ** attempt)
                except ValueError:
                    delay = 0.5 * (2 ** attempt)
                time.sleep(delay)
                continue
            response.raise_for_status()
            payload = response.json()
            break

        if payload is None:
            raise RuntimeError(f"Weather provider did not return data: {last_error}")

        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temperatures = hourly.get("temperature_2m") or []
        codes = hourly.get("weather_code") or []
        if not times:
            raise ValueError("Weather provider returned no hourly forecast")

        index = min(
            range(len(times)),
            key=lambda i: abs(
                (
                    datetime.fromisoformat(times[i]) - target_time
                ).total_seconds()
            ),
        )
        temperature = temperatures[index] if index < len(temperatures) else None
        code = codes[index] if index < len(codes) else None
        condition = _weather_category(code, temperature)

        result = {
            "condition_used": condition,
            "source": "open_meteo_forecast",
            "forecast_available": True,
            "fallback_used": False,
            "fallback_reason": None,
            "forecast_time": times[index],
            "cache_hit": False,
        }
        _weather_cache_set(key, result)
        return result

    except Exception as exc:
        logger.warning("Weather lookup failed for %s %02d:00: %s", trip_date, hour, exc)
        return {
            "condition_used": "Clear",
            "source": "fallback",
            "forecast_available": False,
            "fallback_used": True,
            "fallback_reason": "weather_provider_unavailable",
        }


def get_weather_condition(
    lat: float,
    lon: float,
    depart_min: int,
    trip_date: Date,
) -> str:
    """Backward-compatible weather helper returning only the model category."""
    return get_weather_details(lat, lon, depart_min, trip_date)["condition_used"]


@dataclass
class RouteOption:
    distance_km: float
    free_min: float
    coords: list  # [[latitude, longitude], ...]


class OsrmClient:
    """OSRM client with bounded retries and a per-instance TTL cache."""

    def __init__(
        self,
        base_url: str = "http://localhost:5000",
        timeout: float = 4.0,
        cache_ttl_seconds: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds or settings.OSRM_CACHE_TTL_SECONDS
        self._cache: dict[tuple, tuple[float, list[RouteOption]]] = {}
        self._cache_lock = Lock()

    def routes(self, a, b) -> list[RouteOption]:
        key = (
            round(a[0], 5), round(a[1], 5),
            round(b[0], 5), round(b[1], 5),
        )
        now = time.monotonic()
        with self._cache_lock:
            cached = self._cache.get(key)
            if cached:
                expiry, routes = cached
                if expiry > now:
                    return list(routes)
                self._cache.pop(key, None)

        url = f"{self.base_url}/route/v1/driving/{a[1]},{a[0]};{b[1]},{b[0]}"
        params = {
            "alternatives": "true",
            "overview": "full",
            "geometries": "geojson",
        }

        try:
            import httpx

            payload = None
            for attempt in range(3):
                response = httpx.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                    headers={"User-Agent": "RouteSense-backend"},
                )
                if response.status_code == 429 or response.status_code in {500, 502, 503, 504}:
                    if attempt == 2:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = min(2.0, max(0.0, float(retry_after))) if retry_after else 0.25 * (2 ** attempt)
                    except ValueError:
                        delay = 0.25 * (2 ** attempt)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                break

            if payload is None:
                return []

            routes: list[RouteOption] = []
            for route in payload.get("routes", []):
                coordinates = route.get("geometry", {}).get("coordinates", [])
                if not coordinates:
                    continue
                routes.append(
                    RouteOption(
                        distance_km=float(route["distance"]) / 1000,
                        free_min=float(route["duration"]) / 60,
                        coords=[[float(lat), float(lon)] for lon, lat in coordinates],
                    )
                )

            if routes:
                with self._cache_lock:
                    self._cache[key] = (
                        time.monotonic() + max(60, self.cache_ttl_seconds),
                        list(routes),
                    )
            return routes

        except Exception as exc:
            logger.warning("OSRM route request failed: %s", exc)
            return []


def score_options(
    options: list[RouteOption],
    start,
    end,
    depart_min: int,
    date: Date,
    weather_condition: str = "Clear",
) -> list[dict]:
    """Score OSRM alternatives using the trained model, not free-flow ETA."""
    scored = []
    for option in options:
        try:
            eta = predict_travel_time(
                start_lat=start[0],
                start_lon=start[1],
                end_lat=end[0],
                end_lon=end[1],
                distance_km=option.distance_km,
                depart_min=depart_min,
                date=date,
                weather_condition=weather_condition,
            )
            prediction_source = "ml"
        except Exception:
            logger.exception("ML prediction failed for an OSRM route alternative")
            eta = None
            prediction_source = "unavailable"

        scored.append({
            "distance_km": round(option.distance_km, 2),
            "osrm_duration_min": round(option.free_min, 1),
            "eta_min": round(eta, 1) if eta is not None else None,
            "prediction_source": prediction_source,
        })
    return scored


def _mins(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _hhmm(total_minutes: int) -> str:
    total_minutes = int(total_minutes) % (24 * 60)
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def add_routes(
    plan: dict,
    start=None,
    osrm: OsrmClient | None = None,
    congestion=None,
) -> dict:
    """Attach real OSRM geometry and ML ETA to each consecutive stop leg.

    The first stop of each day is the origin and has no incoming leg.
    For every later stop, departure is the previous stop's scheduled
    departure. The ML estimate updates the next stop's schedule before
    the following leg is calculated, so all ETAs are computed upfront
    against a consistent, sequential itinerary.
    """
    heuristic = HeuristicTravel(congestion)
    used_osrm = 0
    total_legs = 0
    warnings = plan.setdefault("warnings", [])

    for day in plan.get("days", []):
        stops = day.get("stops", [])
        trip_date = Date.fromisoformat(day["date"])
        weekday = trip_date.weekday()

        if not stops:
            day["route_eta_total_min"] = 0
            day["travel_km"] = 0.0
            continue

        first = stops[0]
        first_location = (float(first["lat"]), float(first["lon"]))
        first["travel_minutes_from_previous"] = 0
        first["travel_km"] = 0.0
        first["transport_inr"] = 0
        first["route"] = {
            "source": "origin",
            "distance_km": 0.0,
            "osrm_duration_min": None,
            "eta_min": 0,
            "prediction_source": "none",
            "delta_min": 0,
            "depart": first["arrive"],
            "from": {"lat": first_location[0], "lon": first_location[1]},
            "polyline": [],
            "geometry": None,
            "weather": None,
            "alternatives": [],
        }

        previous = first
        route_eta_total = 0
        day_distance_total = 0.0
        day_transport_total = sum(
            float(stop.get("transport_inr") or 0) for stop in stops
        )

        for stop in stops[1:]:
            previous_location = (float(previous["lat"]), float(previous["lon"]))
            destination = (float(stop["lat"]), float(stop["lon"]))
            depart_min = _mins(previous["leave"])
            planned_travel_min = int(stop.get("travel_minutes_from_previous") or 0)

            weather = get_weather_details(
                lat=destination[0],
                lon=destination[1],
                depart_min=depart_min,
                trip_date=trip_date,
            )

            options = osrm.routes(previous_location, destination) if osrm else []
            geometry = None
            osrm_duration = None
            alternatives: list[dict] = []
            distance_source = "heuristic_estimate"

            if options:
                alternatives = score_options(
                    options,
                    previous_location,
                    destination,
                    depart_min,
                    trip_date,
                    weather_condition=weather["condition_used"],
                )
                usable = [
                    (index, item)
                    for index, item in enumerate(alternatives)
                    if item["eta_min"] is not None
                ]
                if usable:
                    best_index, best = min(usable, key=lambda pair: pair[1]["eta_min"])
                    selected_option = options[best_index]
                    eta_min = max(1, round(best["eta_min"]))
                    osrm_duration = best["osrm_duration_min"]
                    distance_km = best["distance_km"]
                    geometry = {
                        "type": "LineString",
                        "coordinates": [
                            [lon, lat] for lat, lon in selected_option.coords
                        ],
                    }
                    distance_source = "osrm"
                    prediction_source = "ml"
                    for index, item in enumerate(alternatives):
                        item["chosen"] = index == best_index
                    used_osrm += 1
                else:
                    # If the model is unavailable, retain OSRM's road duration.
                    best_index = min(
                        range(len(options)),
                        key=lambda index: options[index].free_min,
                    )
                    selected_option = options[best_index]
                    eta_min = max(1, round(selected_option.free_min))
                    osrm_duration = round(selected_option.free_min, 1)
                    distance_km = round(selected_option.distance_km, 2)
                    geometry = {
                        "type": "LineString",
                        "coordinates": [
                            [lon, lat] for lat, lon in selected_option.coords
                        ],
                    }
                    distance_source = "osrm"
                    prediction_source = "osrm_freeflow_fallback"
                    warnings.append(
                        f"Day {day['day']}: ML prediction unavailable for the leg to {stop['name']}; OSRM duration was used."
                    )
            else:
                # No straight-line geometry is returned as if it were a road route.
                _, estimated_km = heuristic.leg(
                    previous_location,
                    destination,
                    depart_min,
                    weekday,
                    trip_date,
                )
                distance_km = round(estimated_km, 2)
                try:
                    eta_min = max(
                        1,
                        round(
                            predict_travel_time(
                                start_lat=previous_location[0],
                                start_lon=previous_location[1],
                                end_lat=destination[0],
                                end_lon=destination[1],
                                distance_km=distance_km,
                                depart_min=depart_min,
                                date=trip_date,
                                weather_condition=weather["condition_used"],
                            )
                        ),
                    )
                    prediction_source = "ml"
                except Exception:
                    eta_min, _ = heuristic.leg(
                        previous_location,
                        destination,
                        depart_min,
                        weekday,
                        trip_date,
                    )
                    prediction_source = "heuristic_fallback"
                warnings.append(
                    f"Day {day['day']}: OSRM geometry unavailable for the leg to {stop['name']}."
                )

            actual_arrival = depart_min + eta_min
            duration = int(stop.get("visit_minutes") or 60)
            hours_table = parse_hours(stop.get("opening_hours"))
            fit = fit_visit(
                hours_table,
                weekday,
                actual_arrival,
                duration,
                max_wait=180,
                min_frac=0.6,
            )
            if fit:
                scheduled_start, scheduled_end = fit
                stop["actual_arrival"] = _hhmm(actual_arrival)
                stop["arrive"] = _hhmm(scheduled_start)
                stop["display_arrive"] = _hhmm(scheduled_start)
                stop["leave"] = _hhmm(scheduled_end)
                stop["schedule_conflict"] = False
            else:
                stop["actual_arrival"] = _hhmm(actual_arrival)
                stop["arrive"] = _hhmm(actual_arrival)
                stop["display_arrive"] = _hhmm(actual_arrival)
                stop["leave"] = _hhmm(actual_arrival + duration)
                stop["schedule_conflict"] = True
                warnings.append(
                    f"Day {day['day']}: predicted arrival at {stop['name']} does not fit its opening hours."
                )

            new_transport = round(distance_km * 12) if distance_km > 1.0 else 0
            day_transport_total += new_transport - int(stop.get("transport_inr") or 0)
            stop["transport_inr"] = new_transport
            stop["travel_minutes_from_previous"] = eta_min
            stop["travel_km"] = round(distance_km, 1)

            route = {
                "source": "osrm" if geometry else "unavailable",
                "distance_source": distance_source,
                "distance_km": distance_km,
                "osrm_duration_min": osrm_duration,
                "eta_min": eta_min,
                "prediction_source": prediction_source,
                "delta_min": eta_min - planned_travel_min,
                "depart": _hhmm(depart_min),
                "from": {"lat": previous_location[0], "lon": previous_location[1]},
                "polyline": (
                    [[lat, lon] for lon, lat in geometry["coordinates"]]
                    if geometry else []
                ),
                "geometry": geometry,
                "weather": weather,
                "alternatives": alternatives,
            }
            stop["route"] = route

            route_eta_total += eta_min
            day_distance_total += distance_km
            total_legs += 1
            previous = stop

        day["route_eta_total_min"] = route_eta_total
        day["travel_km"] = round(day_distance_total, 1)
        day["spend_inr"] = round(
            sum(float(stop.get("cost_inr") or 0) + float(stop.get("transport_inr") or 0) for stop in stops)
        )

    if used_osrm == total_legs and total_legs:
        routing_source = "osrm"
    elif used_osrm:
        routing_source = "partial"
    else:
        routing_source = "unavailable"

    plan["routing"] = {
        "source": routing_source,
        "geometry_available": used_osrm > 0,
        "legs_with_osrm_geometry": used_osrm,
        "total_legs": total_legs,
    }

    summary = plan.get("summary", {})
    summary["total_spend_inr"] = round(
        sum(day.get("spend_inr", 0) for day in plan.get("days", []))
    )
    summary["total_travel_km"] = round(
        sum(day.get("travel_km", 0) for day in plan.get("days", [])), 1
    )
    if summary.get("budget_inr") is not None:
        summary["within_budget"] = (
            summary["total_spend_inr"] <= float(summary["budget_inr"]) + 1
        )
        if not summary["within_budget"]:
            warnings.append("Plan exceeds the specified budget after route recalculation.")

    return plan


def resolve_start(user_lat, user_lon, centre):
    """Deprecated compatibility helper; itinerary generation does not use GPS or city centre."""
    return None, "first_stop"


def to_frontend(
    plan: dict,
    prompt: str = "",
    start=None,
    start_source: str = "first_stop",
    trip_id: str | None = None,
) -> dict:
    """Convert the planner result to the legacy frontend response shape."""
    trip_id = trip_id or uuid.uuid4().hex[:10]
    days = []

    for day in plan["days"]:
        day_id = f"{trip_id}-d{day['day']}"
        stops = []
        for stop in day["stops"]:
            route = stop.get("route") or {}
            polyline = route.get("polyline") or []
            route_from = route.get("from")
            stops.append({
                "id": f"{day_id}-{stop['id']}",
                "poiId": stop["id"],
                "name": stop["name"],
                "time": stop["arrive"],
                "leaveTime": stop["leave"],
                "description": stop.get("description") or "",
                "visitMinutes": stop["visit_minutes"],
                "coordinates": [stop["lon"], stop["lat"]],
                "kind": stop["kind"],
                "category": stop["category"],
                "source": stop["source"],
                "sources": stop.get("sources", []),
                "score": stop.get("score"),
                "baseScore": stop.get("base_score"),
                "scoreMethod": stop.get("score_method"),
                "matchedPreferences": stop.get("matched_preferences", []),
                "costInr": stop["cost_inr"],
                "transportInr": stop["transport_inr"],
                "openingHours": stop["opening_hours"],
                "note": stop.get("note"),
                "scheduleConflict": stop.get("schedule_conflict", False),
                "route": {
                    "source": route.get("source"),
                    "distanceKm": route.get("distance_km"),
                    "etaMinutes": route.get("eta_min"),
                    "osrmDurationMinutes": route.get("osrm_duration_min"),
                    "predictionSource": route.get("prediction_source"),
                    "deltaMinutes": route.get("delta_min"),
                    "departTime": route.get("depart"),
                    "from": [route_from["lon"], route_from["lat"]] if route_from else None,
                    "geometry": route.get("geometry"),
                    "weather": route.get("weather"),
                },
            })

        days.append({
            "id": day_id,
            "label": f"Day {day['day']}",
            "date": day["date"],
            "weekday": day["weekday"],
            "spendInr": day["spend_inr"],
            "travelKm": day["travel_km"],
            "routeEtaTotalMin": day.get("route_eta_total_min"),
            "endsAt": day["ends_at"],
            "stops": stops,
        })

    summary = plan["summary"]
    return {
        "tripId": trip_id,
        "city": plan["city"],
        "prompt": prompt,
        "origin": {
            "coordinates": days[0]["stops"][0]["coordinates"],
            "source": "first_stop",
        } if days and days[0]["stops"] else None,
        "days": days,
        "summary": {
            "totalSpendInr": summary["total_spend_inr"],
            "budgetInr": summary["budget_inr"],
            "withinBudget": summary["within_budget"],
            "perPerson": summary["per_person"],
            "travellers": summary["travellers"],
            "totalTravelKm": summary["total_travel_km"],
        },
        "interests": plan["interests_used"],
        "notScheduled": plan["not_scheduled"],
        "warnings": plan["warnings"],
        "routing": plan.get("routing"),
    }
