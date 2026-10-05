"""Polymarket game events: one event per game, with a 2-outcome 'moneyline' market."""
import json
import time
from datetime import datetime, timedelta, timezone

from .config import CLOB_BASE, GAMMA_BASE


def fetch_game_events(client, series_id: int, days: int = 7, page: int = 50, max_pages: int = 20) -> list[dict]:
    """Upcoming (not yet started) game events for a league series within `days` days."""
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=days)
    games, offset = [], 0
    for _ in range(max_pages):
        params = {"series_id": series_id, "active": "true", "closed": "false", "limit": page, "offset": offset}
        r = client.get(f"{GAMMA_BASE}/events", params=params)
        r.raise_for_status()
        events = r.json()
        for e in events:
            g = parse_game(e)
            if g and now <= g["start"] <= horizon:
                games.append(g)
        if len(events) < page:
            break
        offset += page
        time.sleep(0.2)
    return games


def parse_game(event: dict) -> dict | None:
    teams = event.get("teams") or []
    if len(teams) != 2 or not event.get("startTime") or not event.get("eventDate"):
        return None
    ml = next((m for m in event.get("markets", []) if m.get("sportsMarketType") == "moneyline"), None)
    if not ml or not ml.get("acceptingOrders", True):
        return None
    try:
        outcomes = json.loads(ml["outcomes"]) if isinstance(ml["outcomes"], str) else ml["outcomes"]
        tokens = json.loads(ml["clobTokenIds"]) if isinstance(ml["clobTokenIds"], str) else ml["clobTokenIds"]
    except (KeyError, TypeError, ValueError):
        return None
    if len(outcomes) != 2 or len(tokens) != 2:
        return None
    by_outcome = {o.strip().lower(): t for o, t in zip(outcomes, tokens)}
    out_teams = []
    for t in teams:
        token = by_outcome.get((t.get("alias") or "").strip().lower())
        if token is None:
            return None
        out_teams.append({"name": t.get("name", ""), "alias": t.get("alias", ""), "token": token})
    return {
        "slug": event.get("slug"),
        "us_slug": event.get("usId"),  # same game on Polymarket US, when present
        "date": datetime.strptime(event["eventDate"], "%Y-%m-%d").date(),
        "start": datetime.fromisoformat(event["startTime"].replace("Z", "+00:00")),
        "teams": out_teams,
        "fee_schedule": ml.get("feeSchedule"),
        "rules": ml.get("description", ""),
    }


def best_ask(client, token_id: str) -> tuple[float, float] | None:
    """Best ask (price, size) from the CLOB book. The API lists levels worst-first, so take min()."""
    r = client.get(f"{CLOB_BASE}/book", params={"token_id": token_id})
    if r.status_code == 404:
        return None  # no order book for this token
    r.raise_for_status()
    asks = r.json().get("asks", [])
    if not asks:
        return None
    best = min(asks, key=lambda a: float(a["price"]))
    return float(best["price"]), float(best["size"])
