"""Geoapify POI retrieval, deterministic scoring, matching and source merging."""
from __future__ import annotations

import copy
import logging
import math
import re
import time
import unicodedata
from difflib import SequenceMatcher
from threading import Lock

import requests

from app.config import settings
from .hours import parse_hours
from .pois import POI
from .parser import GROUPS
from .travel import haversine_km

logger = logging.getLogger(__name__)

GEOAPIFY_API_KEY = settings.GEOAPIFY_API_KEY or ""
GEOAPIFY_BASE_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_CACHE_TTL_SECONDS = 24 * 60 * 60
GEOAPIFY_CACHE_MAX_ENTRIES = 256
DUPLICATE_RADIUS_METERS = 100.0

# In-process TTL cache. Successful provider results only are cached.
_geoapify_cache: dict[tuple, tuple[float, list[POI]]] = {}
_geoapify_cache_lock = Lock()

GEOAPIFY_CATEGORY_MAP = {
    "history & heritage": "tourism.sights,building.historic",
    "food": "catering.restaurant,catering.fast_food",
    "cafes": "catering.cafe",
    "shopping": "commercial.marketplace,commercial.shopping_mall",
    "nightlife": "catering.bar,catering.pub",
    "nature & parks": "leisure.park,gardens",
    "religious & spiritual": "building.place_of_worship",
    "family & fun": "entertainment",
}

INTERNAL_CAT_MAP = {
    "history & heritage": "attraction",
    "food": "food",
    "cafes": "cafe",
    "shopping": "shopping",
    "nightlife": "nightlife",
    "nature & parks": "nature",
    "religious & spiritual": "religious",
    "family & fun": "entertainment",
}


def normalize_name(name: str) -> str:
    """Normalize accents, punctuation and whitespace for duplicate matching."""
    normalized = unicodedata.normalize("NFKD", name.casefold())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.replace("gurudwara", "gurdwara").replace("café", "cafe")
    return "".join(ch for ch in normalized if ch.isalnum())


def _name_similarity(left: str, right: str) -> float:
    a, b = normalize_name(left), normalize_name(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sequence_score = SequenceMatcher(None, a, b).ratio()
    token_a = set(re.findall(r"[a-z0-9]+", left.casefold()))
    token_b = set(re.findall(r"[a-z0-9]+", right.casefold()))
    token_score = len(token_a & token_b) / max(1, len(token_a | token_b))
    containment = min(len(a), len(b)) >= 6 and (a in b or b in a)
    return max(sequence_score, token_score, 0.82 if containment else 0.0)


def is_coordinate_duplicate(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    threshold_meters: float = DUPLICATE_RADIUS_METERS,
) -> bool:
    """Return whether two valid coordinates are within the duplicate radius."""
    if any(value is None for value in (lat1, lon1, lat2, lon2)):
        return False
    return haversine_km((float(lat1), float(lon1)), (float(lat2), float(lon2))) * 1000 <= threshold_meters


def _is_same_place(a: POI, b: POI) -> bool:
    """A duplicate requires both a similar name and nearby coordinates."""
    return (
        _name_similarity(a.name, b.name) >= 0.60
        and is_coordinate_duplicate(a.lat, a.lon, b.lat, b.lon)
    )


def calculate_bearing(
    center_lat: float,
    center_lon: float,
    target_lat: float,
    target_lon: float,
) -> float:
    """Calculate compass bearing from the search centre to a POI."""
    lat1, lon1, lat2, lon2 = map(
        math.radians, [center_lat, center_lon, target_lat, target_lon]
    )
    dlon = lon2 - lon1
    x = math.sin(dlon) * math.cos(lat2)
    y = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(dlon)
    )
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def geoapify_score(props: dict) -> float:
    """Return a comparable 0–5 score and expose its scoring provenance.

    Geoapify importance is normalized from [0, 1] to [1, 5]. When it is
    unavailable, a metadata proxy starts at 3 and adds 0.5 for each of
    website, Wikipedia/Wikidata and opening-hours metadata.
    """
    rank = props.get("rank") or {}
    importance = rank.get("importance")
    if importance is not None:
        try:
            score = max(0.0, min(1.0, float(importance)))
            return round(1.0 + 4.0 * score, 1)
        except (TypeError, ValueError):
            pass

    raw = (props.get("datasource") or {}).get("raw") or {}
    score = 3.0
    if props.get("website") or raw.get("website"):
        score += 0.5
    if raw.get("wikipedia") or raw.get("wikidata") or props.get("wiki_and_media"):
        score += 0.5
    if props.get("opening_hours") or raw.get("opening_hours"):
        score += 0.5
    return min(5.0, round(score, 1))


def _cache_key(pref: str, lat: float, lon: float, radius_meters: int) -> tuple:
    return (pref.casefold(), round(lat, 4), round(lon, 4), int(radius_meters))


def _cached_places(key: tuple) -> list[POI] | None:
    now = time.monotonic()
    with _geoapify_cache_lock:
        item = _geoapify_cache.get(key)
        if item is None:
            return None
        expires_at, places = item
        if expires_at <= now:
            _geoapify_cache.pop(key, None)
            return None
        return copy.deepcopy(places)


def _store_places(key: tuple, places: list[POI]) -> None:
    now = time.monotonic()
    with _geoapify_cache_lock:
        expired = [k for k, (expiry, _) in _geoapify_cache.items() if expiry <= now]
        for old_key in expired:
            _geoapify_cache.pop(old_key, None)
        while len(_geoapify_cache) >= GEOAPIFY_CACHE_MAX_ENTRIES:
            oldest = min(_geoapify_cache, key=lambda k: _geoapify_cache[k][0])
            _geoapify_cache.pop(oldest, None)
        _geoapify_cache[key] = (
            now + GEOAPIFY_CACHE_TTL_SECONDS,
            copy.deepcopy(places),
        )


def _request_geoapify(params: dict) -> dict:
    """Call Geoapify with bounded retry for throttling and transient errors."""
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get(
                GEOAPIFY_BASE_URL,
                params=params,
                timeout=8,
                headers={"User-Agent": "RouteSense-backend"},
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
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 2:
                raise
            time.sleep(0.25 * (2 ** attempt))
    if last_error:
        raise last_error
    return {}


def fetch_geoapify_pois(
    pref: str,
    lat: float = 28.6139,
    lon: float = 77.2090,
    radius_meters: int = 12000,
    limit: int = 6,
) -> list[POI]:
    """Fetch up to ``limit`` high-scoring places for one preference."""
    if not GEOAPIFY_API_KEY:
        logger.info("Geoapify disabled: GEOAPIFY_API_KEY is not configured")
        return []

    key = _cache_key(pref, lat, lon, radius_meters)
    cached = _cached_places(key)
    if cached is not None:
        return cached[:limit]

    category = GEOAPIFY_CATEGORY_MAP.get(pref.casefold(), "tourism")
    internal_category = INTERNAL_CAT_MAP.get(pref.casefold(), "attraction")
    params = {
        "categories": category,
        "filter": f"circle:{lon},{lat},{radius_meters}",
        "bias": f"proximity:{lon},{lat}",
        "limit": 20,
        "apiKey": GEOAPIFY_API_KEY,
    }

    try:
        payload = _request_geoapify(params)
        candidates: list[POI] = []
        for index, feature in enumerate(payload.get("features", [])):
            props = feature.get("properties") or {}
            name = props.get("name")
            if not name:
                continue

            score = geoapify_score(props)
            score_method = (
                "geoapify_importance"
                if (props.get("rank") or {}).get("importance") is not None
                else "geoapify_metadata_proxy"
            )
            hours_raw = props.get("opening_hours") or "Mo-Su 09:00-18:00"
            place_lat = props.get("lat")
            place_lon = props.get("lon")
            if place_lat is None or place_lon is None:
                continue

            candidates.append(
                POI(
                    id=f"geoapify_{props.get('place_id', index)}",
                    name=str(name),
                    category=internal_category,
                    lat=float(place_lat),
                    lon=float(place_lon),
                    cost=0.0,
                    duration=60 if internal_category in ("food", "cafe") else 90,
                    popularity=score,
                    tags={"live_api", pref.casefold()},
                    hours_raw=hours_raw,
                    hours=parse_hours(hours_raw),
                    description=props.get("formatted", "Geoapify place"),
                    extra={
                        "source": "geoapify",
                        "sources": ["geoapify"],
                        "provider_id": str(props.get("place_id", index)),
                        "score_method": score_method,
                        "base_score": score,
                        "hours_estimated": not bool(props.get("opening_hours")),
                        "cost_estimated": True,
                        "visit_duration_estimated": True,
                        "website": props.get("website", ""),
                        "wikipedia": (
                            (props.get("datasource") or {}).get("raw", {}).get("wikipedia", "")
                            or (props.get("datasource") or {}).get("raw", {}).get("wikidata", "")
                        ),
                        "matched_preferences": [pref.casefold()],
                    },
                )
            )

        # Stable ranking; no random sampling means repeated prompts are reproducible.
        candidates.sort(key=lambda poi: (-poi.popularity, poi.name.casefold(), poi.id))
        _store_places(key, candidates)
        return candidates[:limit]
    except (requests.RequestException, ValueError, KeyError) as exc:
        logger.warning("Geoapify request failed for preference %s: %s", pref, exc)
        return []


def _matches_interest(poi: POI, interests: list[str]) -> bool:
    if not interests:
        return True
    for interest in interests:
        key = interest.casefold()
        if poi.category == INTERNAL_CAT_MAP.get(key):
            return True
        group = GROUPS.get(key)
        if group and (poi.tags & group[2]):
            return True
    return False


def _top_curated_for_interest(
    base_pois: list[POI],
    interest: str,
    limit: int,
) -> list[POI]:
    matches = [
        copy.deepcopy(poi)
        for poi in base_pois
        if _matches_interest(poi, [interest])
    ]
    matches.sort(key=lambda poi: (-poi.popularity, poi.name.casefold(), poi.id))
    selected = matches[:limit]
    for poi in selected:
        poi.extra.update(
            {
                "source": "curated",
                "sources": ["curated"],
                "score_method": "curated_popularity",
                "base_score": float(poi.popularity),
                "matched_preferences": [interest.casefold()],
            }
        )
    return selected


def get_geoapify_candidate_pois(
    interests: list[str],
    base_pois: list[POI],
    center: tuple[float, float] = (28.6139, 77.2090),
    limit_per_interest: int = 6,
    radius_meters: int = 12000,
) -> list[POI]:
    """Return a deduplicated curated + Geoapify pool, filtered at score >= 4.

    For every preference, select at most ``limit_per_interest`` curated
    records and the same number of Geoapify records. A hybrid match keeps
    the curated record and receives +0.5, capped at 5.0. Duplicate matching
    requires both name similarity and coordinates within 100 metres.
    """
    if not interests:
        return []

    candidates: list[POI] = []
    curated_reference: list[POI] = []

    for interest in interests:
        curated = _top_curated_for_interest(
            base_pois, interest, limit_per_interest
        )
        for poi in curated:
            existing = next((item for item in candidates if item.id == poi.id), None)
            if existing:
                existing.extra.setdefault("matched_preferences", []).append(interest.casefold())
                continue
            candidates.append(poi)
            curated_reference.append(poi)

        live_places = fetch_geoapify_pois(
            interest.casefold(),
            lat=center[0],
            lon=center[1],
            radius_meters=radius_meters,
            limit=limit_per_interest,
        )

        for live in live_places[:limit_per_interest]:
            live.extra.setdefault("matched_preferences", [interest.casefold()])
            curated_match = next(
                (curated_poi for curated_poi in curated_reference if _is_same_place(live, curated_poi)),
                None,
            )
            if curated_match:
                if "geoapify" not in curated_match.extra.setdefault("sources", []):
                    curated_match.extra["sources"].append("geoapify")
                base_score = float(curated_match.extra.get("base_score", curated_match.popularity))
                curated_match.popularity = min(5.0, round(base_score + 0.5, 1))
                curated_match.extra["source"] = "hybrid"
                curated_match.extra["score_method"] = "curated_plus_geoapify_overlap"
                curated_match.extra["overlap_boost"] = 0.5
                prefs = curated_match.extra.setdefault("matched_preferences", [])
                if interest.casefold() not in prefs:
                    prefs.append(interest.casefold())
                continue

            duplicate_live = next(
                (item for item in candidates if _is_same_place(live, item)),
                None,
            )
            if duplicate_live:
                prefs = duplicate_live.extra.setdefault("matched_preferences", [])
                if interest.casefold() not in prefs:
                    prefs.append(interest.casefold())
                continue
            candidates.append(live)

    eligible = [poi for poi in candidates if poi.popularity >= 4.0]
    eligible.sort(
        key=lambda poi: (
            -poi.popularity,
            0 if poi.extra.get("source") == "hybrid" else 1,
            poi.name.casefold(),
            poi.id,
        )
    )

    for poi in eligible:
        poi.extra["bearing"] = calculate_bearing(
            center[0], center[1], poi.lat, poi.lon
        )
    return eligible


# Backwards-compatible name used by the existing trip router.
get_hybrid_poi_candidates = get_geoapify_candidate_pois
