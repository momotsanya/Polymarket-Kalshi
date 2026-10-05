"""Kalshi game-winner markets: one market per team per game, grouped by event_ticker."""
import time
from collections import defaultdict
from datetime import date, datetime

from .config import KALSHI_BASE


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def fetch_series_markets(client, series_ticker: str, max_pages: int = 50) -> list[dict]:
    out, cursor = [], None
    for _ in range(max_pages):
        params = {"series_ticker": series_ticker, "status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        r = client.get(f"{KALSHI_BASE}/markets", params=params)
        r.raise_for_status()
        data = r.json()
        markets = data.get("markets", [])
        out.extend(markets)
        cursor = data.get("cursor")
        if not cursor or not markets:
            break
        time.sleep(0.2)
    return out


def group_events(markets: list[dict]) -> dict[str, list[dict]]:
    events = defaultdict(list)
    for m in markets:
        events[m["event_ticker"]].append(m)
    return events


def event_date(event_ticker: str) -> date | None:
    """KXNFLGAME-26OCT12BUFLAR -> 2026-10-12 (the game's local date)."""
    try:
        return datetime.strptime(event_ticker.split("-")[1][:7], "%y%b%d").date()
    except (IndexError, ValueError):
        return None


def to_game(event_ticker: str, markets: list[dict]) -> dict | None:
    """Two-team games only (exactly two 'X wins' markets). Quotes come straight from the listing."""
    if len(markets) != 2:
        return None
    d = event_date(event_ticker)
    if d is None:
        return None
    teams = []
    for m in markets:
        yes_ask, yes_bid = _f(m.get("yes_ask_dollars")), _f(m.get("yes_bid_dollars"))
        no_ask = _f(m.get("no_ask_dollars"))
        teams.append({
            "name": m.get("yes_sub_title") or "",
            "ticker": m["ticker"],
            "yes_ask": yes_ask,
            "yes_ask_size": _f(m.get("yes_ask_size_fp")),
            "no_ask": no_ask,
            # a NO ask is a resting YES bid, so its size is the YES bid size
            "no_ask_size": _f(m.get("yes_bid_size_fp")) if yes_bid is not None else None,
        })
    return {"event_ticker": event_ticker, "date": d, "teams": teams}
