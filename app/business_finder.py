"""Discover local home-service businesses that need an AI receptionist.

Two sources:
- OpenStreetMap (Nominatim geocoding + Overpass API) — free, no key needed.
- Google Places (New) text search — richer data (ratings, review counts,
  hours); activates automatically when GOOGLE_PLACES_API_KEY is set.

Businesses are scored for "missed-call pain" — the qualification signals
from the Colibri Code cold-call script: no website, no listed evening or
weekend hours, a small review footprint. Those are the owners losing jobs
to voicemail.
"""
import os
import re
import time

import httpx

USER_AGENT = "AIGrowthEngine/1.0 (local business discovery; respectful, low volume)"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
GOOGLE_PLACES_URL = "https://places.googleapis.com/v1/places:searchText"

# vertical -> (OSM tag regex on craft/shop/trade, Google text query)
VERTICALS = {
    "hvac": ("hvac", "HVAC contractor"),
    "plumber": ("plumber|plumbing", "plumber"),
    "roofer": ("roofer|roofing", "roofing contractor"),
    "electrician": ("electrician|electrical", "electrician"),
    "landscaping": ("gardener|landscaping|landscape_gardener", "landscaping company"),
    "cleaning": ("cleaning", "cleaning service"),
}

_geocode_cache: dict[str, dict | None] = {}

# Not service businesses: supply houses, wholesalers, showrooms.
_SUPPLY_RE = re.compile(r"\b(supply|supplies|wholesale|distribut\w*|showroom)\b", re.IGNORECASE)


YELP_URL = "https://api.yelp.com/v3/businesses/search"

# Yelp category aliases per vertical
YELP_CATEGORIES = {
    "hvac": "hvac",
    "plumber": "plumbing",
    "roofer": "roofing",
    "electrician": "electricians",
    "landscaping": "landscaping",
    "cleaning": "homecleaning",
}


def google_places_enabled() -> bool:
    return bool(os.environ.get("GOOGLE_PLACES_API_KEY"))


def yelp_enabled() -> bool:
    return bool(os.environ.get("YELP_API_KEY"))


# ---------------------------------------------------------------- scoring

def _covers_weekend(hours: str) -> bool:
    """Handles OSM ("Mo-Sa 08:00-17:00", "24/7") and Google
    ("Saturday: 8:00 AM – 5:00 PM" / "Saturday: Closed") hour formats."""
    if "24/7" in hours:
        return True
    if "Saturday" in hours or "Sunday" in hours:  # Google weekday descriptions
        return bool(re.search(r"(Saturday|Sunday):\s*(?!Closed)\S", hours))
    return bool(re.search(r"\b(Sa|Su)\b", hours))  # OSM syntax


def _covers_evening(hours: str) -> bool:
    """True when they answer at/after 6pm (or around the clock)."""
    if "24/7" in hours or "Open 24 hours" in hours:
        return True
    # OSM 24h clock: closing 18:00 or later (incl. past-midnight closes)
    if re.search(r"-\s*(1[89]|2[0-3]|0[0-6]):|-\s*24:00", hours):
        return True
    # Google AM/PM: closing 6 PM or later, or past midnight
    return bool(re.search(r"[–—-]\s*(([6-9]|1[01]):[0-5]\d\s*PM|12:[0-5]\d\s*AM)", hours, re.IGNORECASE))


def score_business(*, phone: str, website: str, hours: str,
                   rating: float | None, review_count: int | None) -> tuple[int, list[str]]:
    """Score 0-100 for missed-call pain. Returns (score, reasons)."""
    score, reasons = 0, []
    if phone:
        score += 20
        reasons.append("phone listed — cold-callable")
    if not website:
        score += 25
        reasons.append("no website — likely no online booking, phone is their only funnel")
    if not hours:
        score += 10
        reasons.append("no listed hours")
    else:
        if not _covers_weekend(hours):
            score += 15
            reasons.append("closed weekends — emergency calls go to voicemail")
        if not _covers_evening(hours):
            score += 10
            reasons.append("closes before 6pm — after-hours calls missed")
    if review_count is not None:
        if 3 <= review_count <= 100:
            score += 15
            reasons.append(f"established but small ({review_count} reviews) — owner still answers the phone")
        elif review_count < 3:
            score += 5
            reasons.append("very small footprint")
    if rating is not None and rating >= 4.0:
        score += 5
        reasons.append(f"good reputation ({rating}★) — busy enough to miss calls")
    return min(score, 100), reasons


# ---------------------------------------------------------------- OpenStreetMap

def geocode_city(city: str) -> dict | None:
    """Resolve a city name to an Overpass area id. Cached; Nominatim asks
    for max 1 req/sec, and our volume is a handful per discovery run."""
    if city in _geocode_cache:
        return _geocode_cache[city]
    result = None
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=15) as client:
            resp = client.get(NOMINATIM_URL, params={"q": city, "format": "json", "limit": "1"})
            resp.raise_for_status()
            hits = resp.json()
            if hits:
                h = hits[0]
                base = {"relation": 3600000000, "way": 2400000000}.get(h.get("osm_type"))
                if base:
                    result = {"area_id": base + int(h["osm_id"]), "display": h.get("display_name", city)}
    except (httpx.HTTPError, KeyError, ValueError):
        pass
    _geocode_cache[city] = result
    time.sleep(1)  # Nominatim usage policy
    return result


def search_osm(city: str, verticals: list[str], limit: int = 40) -> list[dict]:
    """One Overpass query per city covering all requested verticals."""
    area = geocode_city(city)
    if area is None:
        return []
    tag_re = "|".join(VERTICALS[v][0] for v in verticals if v in VERTICALS)
    if not tag_re:
        return []
    query = f"""
[out:json][timeout:30];
area(id:{area['area_id']})->.a;
(
  nwr(area.a)["craft"~"^({tag_re})$"];
);
out center tags {limit};
"""
    results = []
    try:
        with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=45) as client:
            resp = client.post(OVERPASS_URL, data={"data": query})
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
    except httpx.HTTPError:
        return []

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if not name:
            continue
        # Supply houses / wholesalers get mistagged as craft=* in OSM —
        # they sell to contractors, they don't book service calls.
        if _SUPPLY_RE.search(name):
            continue
        phone = tags.get("phone") or tags.get("contact:phone") or ""
        website = tags.get("website") or tags.get("contact:website") or ""
        hours = tags.get("opening_hours", "")
        raw_kind = tags.get("craft", "")
        vertical = next((v for v in verticals if re.fullmatch(VERTICALS[v][0], raw_kind)), raw_kind)
        score, reasons = score_business(
            phone=phone, website=website, hours=hours, rating=None, review_count=None,
        )
        addr = ", ".join(filter(None, [
            " ".join(filter(None, [tags.get("addr:housenumber"), tags.get("addr:street")])),
            tags.get("addr:city"),
        ]))
        results.append({
            "source": "osm",
            "source_url": f"https://www.openstreetmap.org/{el.get('type', 'node')}/{el.get('id')}",
            "title": name[:300],
            "snippet": " · ".join(filter(None, [addr, f"hours: {hours}" if hours else ""]))[:400],
            "author": "",
            "community": city,
            "kind": "business",
            "phone": phone,
            "website": website,
            "city": city,
            "vertical": vertical,
            "intent_score": score,
            "meta": {"hours": hours, "address": addr, "score_reasons": reasons},
        })
    return results


# ---------------------------------------------------------------- Google Places

def search_google(city: str, verticals: list[str], limit: int = 20) -> list[dict]:
    """Google Places (New) text search — needs GOOGLE_PLACES_API_KEY."""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        return []
    field_mask = ",".join(f"places.{f}" for f in [
        "displayName", "nationalPhoneNumber", "websiteUri", "rating",
        "userRatingCount", "googleMapsUri", "formattedAddress",
        "regularOpeningHours", "businessStatus",
    ])
    results = []
    with httpx.Client(timeout=20) as client:
        for v in verticals:
            if v not in VERTICALS:
                continue
            try:
                resp = client.post(
                    GOOGLE_PLACES_URL,
                    headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
                    json={"textQuery": f"{VERTICALS[v][1]} in {city}", "pageSize": limit},
                )
                resp.raise_for_status()
                places = resp.json().get("places", [])
            except httpx.HTTPError:
                continue
            for p in places:
                if p.get("businessStatus") not in (None, "OPERATIONAL"):
                    continue
                name = (p.get("displayName") or {}).get("text", "")
                url = p.get("googleMapsUri", "")
                if not name or not url:
                    continue
                phone = p.get("nationalPhoneNumber", "")
                website = p.get("websiteUri", "")
                hours = "; ".join((p.get("regularOpeningHours") or {}).get("weekdayDescriptions", []))
                rating = p.get("rating")
                review_count = p.get("userRatingCount")
                score, reasons = score_business(
                    phone=phone, website=website, hours=hours,
                    rating=rating, review_count=review_count,
                )
                results.append({
                    "source": "google",
                    "source_url": url,
                    "title": name[:300],
                    "snippet": " · ".join(filter(None, [
                        p.get("formattedAddress", ""),
                        f"{rating}★ ({review_count} reviews)" if rating else "",
                    ]))[:400],
                    "author": "",
                    "community": city,
                    "kind": "business",
                    "phone": phone,
                    "website": website,
                    "city": city,
                    "vertical": v,
                    "intent_score": score,
                    "meta": {
                        "hours": hours, "rating": rating, "review_count": review_count,
                        "address": p.get("formattedAddress", ""), "score_reasons": reasons,
                    },
                })
    return results


# ---------------------------------------------------------------- Yelp

def search_yelp(city: str, verticals: list[str], limit: int = 20) -> list[dict]:
    """Yelp Fusion search — needs YELP_API_KEY (free tier is plenty)."""
    api_key = os.environ.get("YELP_API_KEY")
    if not api_key:
        return []
    results = []
    with httpx.Client(timeout=20, headers={"Authorization": f"Bearer {api_key}"}) as client:
        for v in verticals:
            cat = YELP_CATEGORIES.get(v)
            if not cat:
                continue
            try:
                resp = client.get(YELP_URL, params={
                    "categories": cat, "location": city, "limit": limit,
                    "sort_by": "review_count",
                })
                resp.raise_for_status()
                businesses = resp.json().get("businesses", [])
            except httpx.HTTPError:
                continue
            for b in businesses:
                name, url = b.get("name", ""), b.get("url", "").split("?")[0]
                if not name or not url or b.get("is_closed"):
                    continue
                phone = b.get("display_phone") or b.get("phone") or ""
                rating = b.get("rating")
                review_count = b.get("review_count")
                # Yelp search results omit website/hours — those are unknown here,
                # not absent, so score only what we actually know.
                score, reasons = 0, []
                if phone:
                    score += 20
                    reasons.append("phone listed — cold-callable")
                if review_count is not None and 3 <= review_count <= 100:
                    score += 15
                    reasons.append(f"established but small ({review_count} reviews) — owner still answers the phone")
                if rating is not None and rating >= 4.0:
                    score += 5
                    reasons.append(f"good reputation ({rating}★) — busy enough to miss calls")
                addr = ", ".join((b.get("location") or {}).get("display_address", []))
                results.append({
                    "source": "yelp",
                    "source_url": url,
                    "title": name[:300],
                    "snippet": " · ".join(filter(None, [
                        addr, f"{rating}★ ({review_count} reviews)" if rating else "",
                    ]))[:400],
                    "author": "",
                    "community": city,
                    "kind": "business",
                    "phone": phone,
                    "website": "",
                    "city": city,
                    "vertical": v,
                    "intent_score": score,
                    "meta": {"rating": rating, "review_count": review_count,
                             "address": addr, "score_reasons": reasons},
                })
    return results


# ---------------------------------------------------------------- entry point

def discover(cities: list[str], verticals: list[str], sources: list[str]) -> list[dict]:
    """Find businesses across cities/sources; dedupe by URL, best score wins."""
    seen: dict[str, dict] = {}
    for city in cities[:3]:  # cap request volume
        found = []
        if "osm" in sources:
            found += search_osm(city, verticals)
        if "google" in sources:
            found += search_google(city, verticals)
        if "yelp" in sources:
            found += search_yelp(city, verticals)
        for biz in found:
            url = biz["source_url"]
            if url not in seen or biz["intent_score"] > seen[url]["intent_score"]:
                seen[url] = biz
    return sorted(seen.values(), key=lambda x: x["intent_score"], reverse=True)
