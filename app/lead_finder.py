"""Discover potential customers from public sources (Reddit, Hacker News).

Both sources are free public JSON APIs — no keys required. Results are
scored for buying intent so the hottest leads float to the top.
"""
import os
import re
import time

import httpx

USER_AGENT = "AIGrowthEngine/1.0 (lead discovery; respectful, low volume)"
BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Reddit app-only OAuth token cache (client-credentials grant).
_reddit_token: dict = {"value": "", "expires": 0.0}


def reddit_oauth_enabled() -> bool:
    return bool(os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))


def bluesky_enabled() -> bool:
    return True  # public search API, no credentials needed

# Phrases that signal someone is actively looking for help / a solution.
INTENT_PHRASES = [
    r"how (do|can|should) i",
    r"looking for",
    r"any (recommendation|advice|tips|ideas)",
    r"recommend",
    r"help me",
    r"where (do|can) i start",
    r"is it (possible|worth)",
    r"struggling",
    r"want to (make|earn|start|learn|grow)",
    r"trying to (make|earn|start|learn|grow)",
    r"best way to",
    r"has anyone",
    r"advice",
    r"beginner",
    r"getting started",
    r"side hustle",
    r"extra (money|income|cash)",
]
_INTENT_RE = [re.compile(p, re.IGNORECASE) for p in INTENT_PHRASES]


def score_lead(title: str, snippet: str, created_utc: float, engagement: int) -> int:
    """Score 0-100 for buying intent."""
    text = f"{title} {snippet}"
    score = 0
    # Intent phrases: up to 60 points
    hits = sum(1 for rx in _INTENT_RE if rx.search(text))
    score += min(hits * 15, 60)
    # Question marks signal someone seeking answers
    if "?" in title:
        score += 10
    # Recency: up to 20 points (fresh in the last 7 days)
    age_days = max(0.0, (time.time() - created_utc) / 86400)
    if age_days <= 1:
        score += 20
    elif age_days <= 3:
        score += 12
    elif age_days <= 7:
        score += 6
    # Engagement: up to 10 points
    score += min(engagement // 5, 10)
    return min(score, 100)


def _reddit_access_token() -> str:
    """App-only OAuth token (client-credentials). Cached until ~1 min before expiry.
    OAuth avoids the 403 that Reddit returns for anonymous www.reddit.com traffic."""
    if not reddit_oauth_enabled():
        return ""
    if _reddit_token["value"] and time.time() < _reddit_token["expires"]:
        return _reddit_token["value"]
    try:
        resp = httpx.post(
            "https://www.reddit.com/api/v1/access_token",
            data={"grant_type": "client_credentials"},
            auth=(os.environ["REDDIT_CLIENT_ID"], os.environ["REDDIT_CLIENT_SECRET"]),
            headers={"User-Agent": USER_AGENT}, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        _reddit_token["value"] = data["access_token"]
        _reddit_token["expires"] = time.time() + int(data.get("expires_in", 3600)) - 60
        return _reddit_token["value"]
    except (httpx.HTTPError, KeyError):
        return ""


def search_reddit(keyword: str, subreddits: list[str], limit: int = 25) -> list[dict]:
    """Search Reddit. Uses app-only OAuth (oauth.reddit.com) when
    REDDIT_CLIENT_ID/SECRET are set — anonymous www.reddit.com search
    otherwise 403s. Falls back to anonymous, which usually returns nothing."""
    results = []
    token = _reddit_access_token()
    host = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    headers = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    suffix = "" if token else ".json"  # oauth host serves JSON without the extension
    urls = [(f"{host}/search{suffix}", {"q": keyword, "sort": "new", "limit": str(limit), "t": "month"})]
    for sub in subreddits[:3]:
        urls.append((
            f"{host}/r/{sub}/search{suffix}",
            {"q": keyword, "restrict_sr": "1", "sort": "new", "limit": "10", "t": "month"},
        ))

    with httpx.Client(headers=headers, timeout=15, follow_redirects=True) as client:
        for url, params in urls:
            try:
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    d = child.get("data", {})
                    permalink = d.get("permalink", "")
                    if not permalink:
                        continue
                    snippet = (d.get("selftext") or "")[:400]
                    results.append({
                        "source": "reddit",
                        "source_url": f"https://www.reddit.com{permalink}",
                        "title": d.get("title", "")[:300],
                        "snippet": snippet,
                        "author": d.get("author", ""),
                        "community": f"r/{d.get('subreddit', '')}",
                        "intent_score": score_lead(
                            d.get("title", ""), snippet,
                            d.get("created_utc", 0),
                            int(d.get("score", 0)) + int(d.get("num_comments", 0)),
                        ),
                    })
            except httpx.HTTPError:
                continue
    return results


def search_hackernews(keyword: str, limit: int = 25) -> list[dict]:
    """Search Hacker News via the free Algolia API."""
    results = []
    since = int(time.time()) - 30 * 86400
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                "https://hn.algolia.com/api/v1/search_by_date",
                params={
                    "query": keyword,
                    "tags": "(story,ask_hn,comment)",
                    "numericFilters": f"created_at_i>{since}",
                    "hitsPerPage": str(limit),
                },
            )
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                object_id = hit.get("objectID")
                if not object_id:
                    continue
                title = hit.get("title") or hit.get("story_title") or ""
                text = re.sub(r"<[^>]+>", " ", hit.get("comment_text") or hit.get("story_text") or "")[:400]
                if not title and not text:
                    continue
                results.append({
                    "source": "hackernews",
                    "source_url": f"https://news.ycombinator.com/item?id={object_id}",
                    "title": (title or text[:120])[:300],
                    "snippet": text,
                    "author": hit.get("author", ""),
                    "community": "Hacker News",
                    "intent_score": score_lead(
                        title, text,
                        hit.get("created_at_i", 0),
                        int(hit.get("points") or 0) + int(hit.get("num_comments") or 0),
                    ),
                })
    except httpx.HTTPError:
        pass
    return results


def search_bluesky(keyword: str, limit: int = 25) -> list[dict]:
    """Search Bluesky's public post index — no auth, no key, no rate-limit pain.
    A strong replacement for Reddit when Reddit isn't authenticated."""
    results = []
    # Browser-like headers — the public AppView edge rejects bare API user-agents.
    headers = {"User-Agent": BROWSER_UA, "Accept": "application/json"}
    try:
        with httpx.Client(timeout=15, headers=headers) as client:
            resp = client.get(
                "https://api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": keyword, "limit": str(min(limit, 25)), "sort": "latest"},
            )
            resp.raise_for_status()
            for post in resp.json().get("posts", []):
                rec = post.get("record", {})
                text = (rec.get("text") or "")[:400]
                if not text:
                    continue
                author = post.get("author", {})
                handle = author.get("handle", "")
                # at://did/app.bsky.feed.post/rkey  ->  bsky.app/profile/handle/post/rkey
                rkey = post.get("uri", "").rsplit("/", 1)[-1]
                url = f"https://bsky.app/profile/{handle}/post/{rkey}" if rkey else post.get("uri", "")
                created = rec.get("createdAt", "")
                try:
                    created_utc = time.mktime(time.strptime(created[:19], "%Y-%m-%dT%H:%M:%S"))
                except (ValueError, TypeError):
                    created_utc = time.time()
                engagement = int(post.get("likeCount") or 0) + int(post.get("replyCount") or 0)
                results.append({
                    "source": "bluesky",
                    "source_url": url,
                    "title": text[:120],
                    "snippet": text,
                    "author": handle,
                    "community": "Bluesky",
                    "intent_score": score_lead(text[:120], text, created_utc, engagement),
                })
    except httpx.HTTPError:
        pass
    return results


def discover(keywords: list[str], subreddits: list[str], sources: list[str]) -> list[dict]:
    """Run discovery across sources for each keyword; dedupe by URL."""
    seen: dict[str, dict] = {}
    for kw in keywords[:4]:  # cap request volume
        found = []
        if "reddit" in sources:
            found += search_reddit(kw, subreddits)
        if "hackernews" in sources:
            found += search_hackernews(kw)
        if "bluesky" in sources:
            found += search_bluesky(kw)
        for lead in found:
            url = lead["source_url"]
            if url not in seen or lead["intent_score"] > seen[url]["intent_score"]:
                seen[url] = lead
    leads = sorted(seen.values(), key=lambda x: x["intent_score"], reverse=True)
    return leads
