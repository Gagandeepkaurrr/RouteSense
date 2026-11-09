from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    latitude: float
    longitude: float


class GeoJSONLineString(BaseModel):
    type: Literal["LineString"] = "LineString"
    coordinates: list[tuple[float, float]]


class WeatherMetadata(BaseModel):
    condition_used: str
    source: str
    forecast_available: bool
    fallback_used: bool
    fallback_reason: str | None = None
    forecast_time: str | None = None
    cache_hit: bool | None = None


class ItineraryStopResponse(BaseModel):
    stop_id: str
    poi_id: str
    name: str
    coordinates: Coordinates
    category: str
    score: float
    base_score: float
    score_method: str
    source: str
    sources: list[str]
    matched_preferences: list[str]
    scheduled_arrival: datetime
    scheduled_departure: datetime
    actual_arrival: datetime | None = None
    visit_duration_minutes: int
    estimated_cost_per_person_inr: float
    estimated_cost_group_inr: float
    opening_hours: str | None = None
    opening_hours_estimated: bool = True
    cost_estimated: bool = True
    visit_duration_estimated: bool = True
    schedule_conflict: bool = False


class ItineraryLegResponse(BaseModel):
    leg_number: int
    from_stop_id: str
    to_stop_id: str
    departure_time: datetime
    distance_km: float
    distance_source: str
    osrm_duration_minutes: float | None = None
    predicted_duration_minutes: int
    prediction_source: str
    geometry: GeoJSONLineString | None = None
    weather: WeatherMetadata


class ItineraryDayResponse(BaseModel):
    day_number: int
    date: date
    origin_stop_id: str
    stops: list[ItineraryStopResponse]
    legs: list[ItineraryLegResponse]
    total_distance_km: float
    total_travel_minutes: int
    estimated_cost_group_inr: float
    schedule_conflicts: int = 0


class TripDetailsResponse(BaseModel):
    city: Literal["Delhi"] = "Delhi"
    start_date: date
    number_of_days: int
    budget_per_person_inr: float
    total_group_budget_inr: float
    number_of_travellers: int
    timezone: str = "Asia/Kolkata"
    preferences: list[str]
    pace: Literal["relaxed", "normal", "packed"]


class ItinerarySummaryResponse(BaseModel):
    estimated_cost_per_person_inr: float
    estimated_cost_group_inr: float
    budget_remaining_per_person_inr: float
    within_budget: bool
    total_distance_km: float
    total_travel_minutes: int
    total_stops: int


class GeneratedItineraryResponse(BaseModel):
    status: Literal["generated"] = "generated"
    trip_id: int
    trip: TripDetailsResponse
    summary: ItinerarySummaryResponse
    days: list[ItineraryDayResponse]
    warnings: list[str] = Field(default_factory=list)
    not_scheduled: list[str] = Field(default_factory=list)


class InsufficientPoolResponse(BaseModel):
    status: Literal["needs_clarification"] = "needs_clarification"
    reason: Literal["insufficient_places"] = "insufficient_places"
    message: str
    available_places: int
    required_places: int
    extracted: dict
    missing_fields: list[str] = Field(default_factory=lambda: ["preferences"])
    questions: list[dict] = Field(default_factory=list)


class SavedTripListItem(BaseModel):
    trip_id: int
    city: str
    start_date: date
    number_of_days: int
    budget_per_person_inr: float | None
    number_of_travellers: int
    status: str
    created_at: datetime
