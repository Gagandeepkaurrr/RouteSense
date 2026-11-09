"""Itinerary engine: Handles daily clock simulation, budget tracking, meal insertions,
and clockwise spatial routing without requiring external scoring re-ranking.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date as Date, timedelta

from .hours import fit_visit, is_open_on, windows
from .pois import POI
from .travel import HeuristicTravel, haversine_km

SIGHT_CATS = {"attraction", "religious", "nature", "entertainment", "shopping"}
MEAL_CATS = {"food", "cafe"}
PACE_ACTIVE_MIN = {"relaxed": 300, "normal": 420, "packed": 540}   # Sightseeing + travel minutes per day
PACE_STOPS = {"relaxed": 4, "normal": 5, "packed": 6}                # Target stops/day
TRANSPORT_INR_PER_KM = 12.0                                         # Cab/Auto rate estimate
DAY_START, LUNCH_FROM, SNACK_FROM = 9 * 60, 12 * 60, 16 * 60
DINNER_FROM, SIGHT_UNTIL = 19 * 60, 18 * 60 + 30
# No external start location: the first scheduled stop is each day's origin.


@dataclass
class TripRequest:
    days: int = 1
    budget_total_inr: float | None = None
    interests: list[str] = field(default_factory=list)
    start_date: Date | None = None
    start_time: str = "09:00"
    pace: str = "normal"
    travellers: int = 1
    start_location: tuple[float, float] | None = None
    default_daily_budget: float = 3000.0
    city: str = "Delhi"


# ----------------------------------------------------------------- Helpers
def _hhmm(m: int) -> str:
    m = int(m)
    return f"{(m // 60) % 24:02d}:{m % 60:02d}"



def round_time_30(total_minutes: int) -> str:
    """Round arrival times up to the next 30-minute boundary."""
    rounded_minutes = ((total_minutes + 29) // 30) * 30
    rounded_minutes %= 24 * 60
    return _hhmm(rounded_minutes)



# ----------------------------------------------------------------- Engine Context
class _Ctx:
    def __init__(self, pois: list[POI], req: TripRequest, travel: HeuristicTravel):
        self.req = req
        self.travel = travel
        self.day_budget = (req.budget_total_inr / req.days) if req.budget_total_inr else req.default_daily_budget
        self.n = max(1, req.travellers)
        
        # Filter POIs strictly for quality scores >= 4.0
        self.pois = [p for p in pois if p.popularity >= 4.0]
        self.pois_by_id = {p.id: p for p in self.pois}


def _shortlist(ctx: _Ctx, sights: list[POI], target: int) -> list[POI]:
    """Shortlists top high-scoring and hybrid-matched sightseeing POIs."""
    # Prioritize hybrid matches and 5.0 ratings first, then 4.0 ratings
    sorted_sights = sorted(
        sights,
        key=lambda p: (
            1 if p.extra.get("source") == "hybrid" or "Hybrid Match" in p.extra.get("source", "") else 0,
            p.popularity
        ),
        reverse=True
    )
    return sorted_sights[:target]

def _cluster_by_location(pois: list[POI], k: int, start) -> list[list[POI]]:
    """Group POIs into k geographic clusters (one per day) with simple k-means."""
    if k <= 1 or not pois:
        return [list(pois)] + [[] for _ in range(max(0, k - 1))]
    if len(pois) <= k:
        return [[p] for p in pois] + [[] for _ in range(k - len(pois))]

    # farthest-point initialisation (deterministic)
    cents = [max(pois, key=lambda p: p.popularity).loc]
    while len(cents) < k:
        far = max(pois, key=lambda p: min(haversine_km(p.loc, c) for c in cents))
        cents.append(far.loc)

    groups: list[list[POI]] = [[] for _ in range(k)]
    for _ in range(15):
        groups = [[] for _ in range(k)]
        for p in pois:
            i = min(range(k), key=lambda i: haversine_km(p.loc, cents[i]))
            groups[i].append(p)
        new = [
            (sum(p.lat for p in g) / len(g), sum(p.lon for p in g) / len(g)) if g else cents[i]
            for i, g in enumerate(groups)
        ]
        if new == cents:
            break
        cents = new

    # No user/browser/city-centre origin is used. Order clusters deterministically
    # by their quality and then geographic centroid; each day's first stop becomes
    # that day's own routing origin.
    order = sorted(
        range(k),
        key=lambda i: (
            -sum(p.popularity for p in groups[i]),
            -len(groups[i]),
            cents[i][0],
            cents[i][1],
        ),
    )
    return [groups[i] for i in order]


def plan_trip(pois: list[POI], req: TripRequest, travel=None) -> dict:
    """Main entry point to build a multi-day itinerary."""
    travel = travel or HeuristicTravel()
    ctx = _Ctx(pois, req, travel)
    warnings: list[str] = []

    if req.budget_total_inr is None:
        warnings.append(f"No budget given; assumed ₹{ctx.day_budget:.0f}/day.")
    
    start_date = req.start_date or Date.today()
    stops_per_day = PACE_STOPS.get(req.pace, 4)

    sights = [p for p in ctx.pois if p.category in SIGHT_CATS]
    pool = _shortlist(ctx, sights, target=int(req.days * stops_per_day * 1.6))
    clusters = _cluster_by_location(pool, req.days, start=None)

    used: set[str] = set()
    spent_total, days_out = 0.0, []

    for d in range(req.days):
        date = start_date + timedelta(days=d)
        wd = date.weekday()
        cap = ctx.day_budget * (d + 1) - spent_total          # Unspent budget rolls forward

        own = [p for p in clusters[d] if p.id not in used and is_open_on(p.hours, wd)]
        if own:
            # Preserve the geographic day cluster. Borrowing merely because a
            # cluster has fewer than the target stops can consume every later
            # day's candidates and leave subsequent days empty.
            cands = own
        else:
            # Borrow only when this day's own cluster has no open candidates.
            spill = [
                p
                for i, group in enumerate(clusters)
                if i != d
                for p in group
                if p.id not in used and is_open_on(p.hours, wd)
            ]
            cands = spill

        seed = _pick_seed(ctx, own or cands)
        day = _plan_day(ctx, d + 1, date, wd, cands, used, cap, stops_per_day, warnings, seed=seed)
        spent_total += day["spend_inr"]
        days_out.append(day)

    carry = [p for p in pool if p.id not in used]
    not_scheduled = [p.name for p in carry]
    total_budget = req.budget_total_inr or ctx.day_budget * req.days
    
    if spent_total > total_budget + 1:
        warnings.append("Plan exceeds the specified budget.")

    return {
        "city": req.city,
        "days": days_out,
        "summary": {
            "total_spend_inr": round(spent_total),
            "budget_inr": round(total_budget),
            "within_budget": spent_total <= total_budget + 1,
            "per_person": req.travellers == 1,
            "travellers": req.travellers,
            "total_travel_km": round(sum(x["travel_km"] for x in days_out), 1),
        },
        "interests_used": req.interests,
        "not_scheduled": not_scheduled,
        "warnings": warnings,
    }



def _pick_seed(ctx: _Ctx, cands: list[POI]) -> POI | None:
    """Choose a strong seed, balancing hybrid matches, quality, and nearby POIs."""
    best = None

    for p in cands:
        near = sorted(
            (
                q.popularity
                for q in cands
                if q.id != p.id
                and haversine_km(p.loc, q.loc) <= 4.0
            ),
            reverse=True,
        )[:5]

        is_hybrid = p.extra.get("source") == "hybrid" or "Hybrid Match" in p.extra.get("source", "")
        score = (
            (2.0 if is_hybrid else 0.0)
            + p.popularity
            + 0.05 * sum(near)
        )

        if best is None or score > best[0]:
            best = (score, p)

    return best[1] if best else None



# ----------------------------------------------------------------- Single Day Scheduler
def _plan_day(ctx: _Ctx, day_no: int, date: Date, wd: int, cands: list[POI], used: set[str], budget_cap: float, stops_per_day: int, warnings: list[str], seed: POI | None = None):
    req, travel, n = ctx.req, ctx.travel, ctx.n
    hour, minute = map(int, req.start_time.split(":"))
    cur = hour * 60 + minute
    loc = seed.loc if seed is not None else (cands[0].loc if cands else None)
    spent, km_total = 0.0, 0.0
    stops: list[dict] = []
    done = {"lunch": False, "snack": False, "dinner": False}
    active = 0                                  # Sightseeing + travel minutes so far
    active_cap = PACE_ACTIVE_MIN.get(req.pace, 420)

    def leg_to(p: POI, depart: int):
        if not stops:
            # The first selected POI is the day's origin; no inbound leg exists.
            return 0, 0.0, 0.0
        if loc is None:
            return 0, 0.0, 0.0
        mins, km = travel.leg(loc, p.loc, depart, wd, date)
        return mins, km, (km * TRANSPORT_INR_PER_KM if km > 1.0 else 0.0)

    def commit(p: POI, kind: str, start: int, end: int, mins: int, km: float, transport: float, cost: float, note: str | None = None):
        nonlocal cur, loc, spent, km_total
        used.add(p.id)
        spent += cost + transport
        km_total += km
        
        why = [
            f"popularity {p.popularity:g}/5",
            f"source: {p.extra.get('source', 'Curated CSV')}"
        ]
        display_start = start

        stops.append({
            "id": p.id,
            "name": p.name,
            "kind": kind,
            "category": p.category,
            "source": p.extra.get("source", "curated"),
            "sources": p.extra.get("sources", [p.extra.get("source", "curated")]),
            "score": round(float(p.popularity), 1),
            "base_score": round(float(p.extra.get("base_score", p.popularity)), 1),
            "score_method": p.extra.get("score_method", "curated_popularity"),
            "matched_preferences": p.extra.get("matched_preferences", []),
            "lat": p.lat,
            "lon": p.lon,
            "display_arrive": _hhmm(start),
            "arrive": round_time_30(display_start),
            "leave": _hhmm(end),
            "visit_minutes": end - start,
            "travel_minutes_from_previous": mins,
            "travel_km": round(km, 1),
            "cost_inr": round(cost),
            "transport_inr": round(transport),
            "opening_hours": p.hours_raw or "Mo-Su 09:00-18:00",
            "opening_hours_estimated": bool(p.extra.get("hours_estimated", True)),
            "cost_estimated": bool(p.extra.get("cost_estimated", True)),
            "visit_duration_estimated": bool(p.extra.get("visit_duration_estimated", True)),
            "why": why,
            "note": note,
            "description": p.description,
        })
        cur, loc = end, p.loc

    def remaining():
        return budget_cap - spent

    def pick_meal(kind: str):
        if len(stops) >= 6:
            done[kind] = True
            return
        nonlocal cur
        dur = {"lunch": 60, "snack": 40, "dinner": 75}[kind]
        earliest = DINNER_FROM if kind == "dinner" else 0
        cap_frac = {"lunch": 0.30, "snack": 0.12, "dinner": 0.40}[kind]
        best = None
        
        for p in ctx.pois:
            if p.id in used:
                continue
            if kind == "dinner" and p.category != "food":
                continue
            if kind == "lunch" and p.category not in MEAL_CATS:
                continue
            if kind == "snack" and not (p.category == "cafe" or p.tags & {"sweets", "street_food", "chaat"}):
                continue

            cost = p.cost * n
            mins, km, tr = leg_to(p, cur)
            if cost > ctx.day_budget * cap_frac or cost + tr > remaining():
                continue

            fit = fit_visit(p.hours, wd, max(cur + mins, earliest), dur, max_wait=30, min_frac=0.8)
            if not fit:
                continue

            rank = p.popularity * 5 - mins * 0.8
            if best is None or rank > best[0]:
                best = (rank, p, fit, mins, km, tr, cost)

        if not best:
            done[kind] = True
            return

        _, p, (s, e), mins, km, tr, cost = best
        commit(p, kind, s, e, mins, km, tr, cost)
        done[kind] = True

    def pick_sight(only: POI | None = None):
        best = None
        reserve = (0 if done["lunch"] else 150 * n) + (0 if done["dinner"] else 200 * n)
        
        for p in cands:
            if p.id in used or p.category not in SIGHT_CATS or (only and p.id != only.id):
                continue
            mins, km, tr = leg_to(p, cur)
            cost = p.cost * n
            if cost + tr > remaining() - reserve:
                continue

            arrival_time = cur + mins
            fit = fit_visit(p.hours, wd, arrival_time, p.duration)
            if not fit:
                continue

            s, e = fit

# Do not schedule a sightseeing stop beyond the sightseeing cutoff.
            if s >= SIGHT_UNTIL:
                continue


            rank = p.popularity * 10 - mins * 1.5
            if best is None or rank > best[0]:
                best = (rank, p, s, e, mins, km, tr, cost)

        return best

    # Main Day Planning Loop
    while True:
        if not done["lunch"] and cur >= LUNCH_FROM:
            pick_meal("lunch")
            continue
        if not done["snack"] and SNACK_FROM <= cur < 1080:
            pick_meal("snack")
            continue
        if not done["dinner"] and cur >= 1110:
            pick_meal("dinner")
            continue

        if active < active_cap and cur < SIGHT_UNTIL and len(stops) < 6:
            b = (pick_sight(only=seed) if (seed and not stops) else None) or pick_sight()
            if b:
                _, p, s, e, mins, km, tr, cost = b
                if not done["lunch"] and cur >= 11 * 60 + 30 and e > 14 * 60:
                    pick_meal("lunch")
                    continue
                note = "shortened: closes before full visit" if e - s < p.duration else None
                commit(p, "sight", s, e, mins, km, tr, cost, note)
                active += mins + (e - s)
                continue
        break

    if not done["lunch"]:
        pick_meal("lunch")
    if not done["dinner"]:
        pick_meal("dinner")

    if not stops:
        warnings.append(f"Day {day_no}: nothing could be scheduled (closed or over budget).")

    return {
        "day": day_no,
        "date": date.isoformat(),
        "weekday": date.strftime("%A"),
        "stops": stops,
        "spend_inr": round(spent),
        "budget_cap_inr": round(budget_cap),
        "travel_km": round(km_total, 1),
        "ends_at": stops[-1]["leave"] if stops else None,
    }