"""Turn a free-text prompt into trip parameters with plain Python (no LLM).

    parse_prompt("3 days in Delhi, budget 9k, love history and street food, relaxed")
    -> ParsedTrip(city='delhi', days=3, budget_total_inr=9000, interests=[...], pace='relaxed', ...)

Anything not found is left None / default and listed in `.missing` so the API can ask a follow-up.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as Date, timedelta



# Defined inside parser.py to extract interests directly from free-text prompts
GROUPS: dict[str, tuple[list[str], set[str], set[str]]] = {
    "history & heritage": (
        ["histor", "heritage", "monument", "fort", "ancient", "architect", "mughal", "tomb", "ruin", "unesco", "sightsee", "landmark", "historic"],
        set(), {"history", "heritage", "monument", "fort", "ancient", "tomb"}
    ),
    "food": (
        ["food", "eat", "street food", "cuisine", "restaurant", "foodie", "kebab", "chaat", "dining", "biryani"],
        {"food"}, {"food", "street_food", "chaat", "kebabs"}
    ),
    "cafes": (["cafe", "coffee", "brunch", "bakery", "tea"], {"cafe"}, {"cafe", "cafes"}),
    "shopping": (
        ["shop", "market", "bazaar", "souvenir", "mall", "handicraft", "clothes", "fashion"],
        {"shopping"}, {"shopping", "fashion", "crafts"}
    ),
    "nightlife": (
        ["nightlife", "club", "bar", "party", "pub", "cocktail", "night"],
        {"nightlife"}, {"nightlife", "cocktails"}
    ),
    "nature & parks": (
        ["nature", "park", "garden", "outdoor", "bird", "lake", "green", "walk", "trek"],
        {"nature"}, {"nature", "park", "lake"}
    ),
    "religious & spiritual": (
        ["relig", "temple", "spiritual", "mosque", "gurudwara", "church", "pilgrim", "dargah", "worship"],
        {"religious"}, {"religious", "hinduism", "sikhism"}
    ),
    "family & fun": (
        ["family", "kid", "child", "fun", "amusement", "adventure", "entertain", "cinema", "movie"],
        {"entertainment"}, {"family", "kids", "entertainment"}
    )
}

WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
         "eight": 8, "nine": 9, "ten": 10, "a": 1}
MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# Explicitly recognized non-Delhi destinations are rejected by the Delhi-only API.
# Unknown/no city mention defaults to Delhi, as agreed.
CITY_ALIASES = {
    "delhi": "delhi", "new delhi": "delhi", "old delhi": "delhi",
    "south delhi": "delhi", "north delhi": "delhi", "east delhi": "delhi",
    "west delhi": "delhi", "central delhi": "delhi",
    "mumbai": "mumbai", "bombay": "mumbai",
    "jaipur": "jaipur", "agra": "agra", "goa": "goa",
    "gurgaon": "gurugram", "gurugram": "gurugram",
    "noida": "noida", "faridabad": "faridabad", "ghaziabad": "ghaziabad",
    "chandigarh": "chandigarh", "amritsar": "amritsar", "ludhiana": "ludhiana",
    "jalandhar": "jalandhar", "dehradun": "dehradun", "rishikesh": "rishikesh",
    "haridwar": "haridwar", "shimla": "shimla", "manali": "manali",
    "srinagar": "srinagar", "leh": "leh", "varanasi": "varanasi",
    "lucknow": "lucknow", "kanpur": "kanpur", "prayagraj": "prayagraj",
    "udaipur": "udaipur", "jodhpur": "jodhpur", "kota": "kota",
    "ahmedabad": "ahmedabad", "surat": "surat", "vadodara": "vadodara",
    "rajkot": "rajkot", "pune": "pune", "nashik": "nashik",
    "nagpur": "nagpur", "indore": "indore", "bhopal": "bhopal",
    "hyderabad": "hyderabad", "bengaluru": "bengaluru", "bangalore": "bengaluru",
    "chennai": "chennai", "kolkata": "kolkata", "kochi": "kochi",
    "cochin": "kochi", "thiruvananthapuram": "thiruvananthapuram",
    "mysuru": "mysuru", "mysore": "mysuru", "mangalore": "mangaluru",
    "mangaluru": "mangaluru", "ooty": "ooty", "coimbatore": "coimbatore",
    "pondicherry": "puducherry", "puducherry": "puducherry",
    "patna": "patna", "ranchi": "ranchi", "bhubaneswar": "bhubaneswar",
    "guwahati": "guwahati", "darjeeling": "darjeeling", "gangtok": "gangtok",
    "varanasi": "varanasi", "ayodhya": "ayodhya", "mathura": "mathura",
    "vrindavan": "vrindavan", "jammu": "jammu", "kashmir": "srinagar",
    "london": "london", "paris": "paris", "new york": "new york",
    "toronto": "toronto", "dubai": "dubai", "singapore": "singapore",
}


def _city(text: str) -> str:
    """Detect explicit destinations; default to Delhi only when none is stated."""
    aliases = sorted(CITY_ALIASES, key=len, reverse=True)
    known_pattern = r"\b(?:in|to|visit|explore|around|at|and)\s+(?:the\s+)?(" + "|".join(
        re.escape(name) for name in aliases
    ) + r")\b"
    known_matches = re.findall(known_pattern, text)
    normalized_matches = [CITY_ALIASES[name] for name in known_matches]
    unsupported = next((city for city in normalized_matches if city != "delhi"), None)
    if unsupported:
        return unsupported
    if normalized_matches:
        return "delhi"

    # Catch unlisted explicit city names (for example, "3 days in Tokyo").
    # The stop words keep the candidate bounded to the destination phrase.
    generic = re.search(
        r"\b(?:in|to)\s+(?!(?:explore|visit|see|go|travel|eat|try|monuments|food|cafes|parks)\b)(?:the\s+)?([a-z][a-z -]{1,35})",
        text,
    )
    if generic:
        candidate = re.split(
            r"\b(?:with|for|on|from|starting|budget|and|near|during|under|over|"
            r"including|plus|from)\b|[,.;!?]",
            generic.group(1),
            maxsplit=1,
        )[0].strip()
        candidate = re.sub(r"\s+", " ", candidate)
        ignored = {
            "city", "town", "area", "there", "here", "the city", "the area",
            "explore", "visit", "see", "go", "travel", "monuments", "food",
        }
        if candidate and candidate not in ignored:
            return CITY_ALIASES.get(candidate, candidate)
    return "delhi"

def _has_explicit_invalid_date(text: str) -> bool:
    """Detect date-shaped input that failed calendar validation."""
    return bool(
        re.search(r"\b20\d{2}-\d{2}-\d{2}\b", text)
        or re.search(
            r"\b\d{1,2}(?:st|nd|rd|th)?\s+(?:"
            + "|".join(MONTHS) + r")[a-z]*\b",
            text,
        )
    )
NUM = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a)"


@dataclass
class ParsedTrip:
    city: str | None = None
    days: int | None = None
    budget_total_inr: float | None = None
    start_date: Date | None = None
    start_time: str | None = None
    interests: list[str] = field(default_factory=list)
    travellers: int = 1
    pace: str = "normal"
    missing: list[str] = field(default_factory=list)


def _n(tok: str) -> int:
    return int(tok) if tok.isdigit() else WORDS[tok]


def _days(t: str) -> int | None:
    # Match "1 day", "1 days", "for 2 days", "3-day trip"
    m = re.search(r"\b(\d+)\s*-\s*days?\b|\b(\d+)\s*days?\b", t)
    if m:
        num = m.group(1) or m.group(2)
        return int(num)
    
    # Check word-based days
    m_word = re.search(rf"\b{NUM}[\s-]*(?:days?|nights?)\b", t)
    if m_word:
        return _n(m_word.group(1))
        
    if re.search(r"\b(day trip|daytrip|1 day|one day)\b", t):
        return 1
    if re.search(r"\bweekend\b", t):
        return 2
    if re.search(r"\b(a|one)\s+week\b", t) or "week long" in t:
        return 7
    return None


def _money(num: str, suffix: str | None) -> float:
    v = float(num.replace(",", ""))
    s = (suffix or "").lower()
    if s in ("k", "thousand"):
        v *= 1000
    elif s in ("l", "lac", "lakh", "lakhs"):
        v *= 100000
    return v


def _budget(t: str, days: int | None) -> float | None:
    amt = r"(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|lakhs?|lacs?|l)?"
    pats = [
        rf"(?:₹|rs\.?|inr)\s*{amt}",                               # ₹9000, rs 9000
        rf"{amt}\s*(?:rupees|rs\b|inr\b|₹)",                       # 9000 rupees
        rf"budget\s*(?:is|of|:|around|about|approx\.?|under|upto|up to)?\s*{amt}",
        rf"(?:under|within|upto|up to|max(?:imum)?)\s+{amt}\b",
        rf"\b(\d+(?:\.\d+)?)\s*(k|lakhs?|lacs?)\b",                # 9k, 1 lakh
    ]
    for p in pats:
        m = re.search(p, t)
        if m:
            val = _money(m.group(1), m.group(2) if m.lastindex and m.lastindex >= 2 else None)
            if val < 100:                      # "budget 3 days"-style false hits
                continue
            tail = t[m.end(): m.end() + 25]
            if days and re.match(r"\s*(?:/|per|a|each|every)\s*(?:day|night)|\s*daily", tail):
                val *= days                    # per-day budget -> total
            return val
    return None


def _date(t: str, today: Date) -> Date | None:
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        try:
            return Date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    if "day after tomorrow" in t:
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    m = re.search(r"\bnext\s+(" + "|".join(WEEKDAYS) + r")\b", t)
    if m:
        ahead = (WEEKDAYS.index(m[1]) - today.weekday()) % 7 or 7
        return today + timedelta(days=ahead)
    m = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(MONTHS) + r")[a-z]*\b", t) or None
    if m:
        d, mon = int(m[1]), MONTHS[m[2]]
    else:
        m2 = re.search(r"\b(" + "|".join(MONTHS) + r")[a-z]*\s+(\d{1,2})(?:st|nd|rd|th)?\b", t)
        if not m2:
            return None
        d, mon = int(m2[2]), MONTHS[m2[1]]
    try:
        out = Date(today.year, mon, d)
    except ValueError:
        return None
    return out if out >= today else Date(today.year + 1, mon, d)


def _travellers(t: str) -> int:
    if re.search(r"\b(couple|honeymoon|my (wife|husband|girlfriend|boyfriend|partner))\b", t):
        return 2
    m = re.search(rf"\b(?:family of|group of)\s+{NUM}\b", t) or re.search(rf"\b{NUM}\s+(?:people|persons|adults|of us|friends|travell?ers)\b", t)
    if m and m.group(1) != "a":
        return max(1, min(20, _n(m.group(1))))
    return 1


def _interests(t: str) -> list[str]:
    """Names of interest groups whose keywords appear (word-start match, so 'eat' != 'great')."""
    found = []
    for name, (keys, _c, _t) in GROUPS.items():
        if any(re.search(r"\b" + re.escape(k), t) for k in keys):
            found.append(name)
    return found





def _start_time(text: str) -> str | None:
    t = text.lower()

    if not re.search(r"\b(start|starting|begin|beginning|from)\b", t):
        return None

    match = re.search(
        r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b",
        t,
    )
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    period = match.group(3)

    if not 1 <= hour <= 12 or not 0 <= minute <= 59:
        return None

    hour = hour % 12
    if period == "pm":
        hour += 12

    return f"{hour:02d}:{minute:02d}"




def parse_prompt(text: str, today: Date | None = None) -> ParsedTrip:
    t = " ".join(text.lower().replace("₹", " ₹").split())
    today = today or Date.today()
    p = ParsedTrip(city=_city(t), days=_days(t))
    p.start_time = _start_time(t)
    p.budget_total_inr = _budget(t, p.days)
    p.start_date = _date(t, today)
    p.interests = _interests(t)
    p.travellers = _travellers(t)
    if re.search(r"\b(relax|slow|chill|leisure|laid.?back|easy)", t):
        p.pace = "relaxed"
    elif re.search(r"\b(packed|busy|as much as|cover everything|fast.?paced)", t):
        p.pace = "packed"
    for f, v in (("days", p.days),):
        if v is None:
            p.missing.append(f)
    if not p.interests:
        p.missing.append("preferences")
    if _has_explicit_invalid_date(t) and p.start_date is None:
        p.missing.append("invalid_date")
    return p
