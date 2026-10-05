"""One-shot snapshot: match upcoming games across Polymarket and Kalshi and print the best surebet gaps.

    python -m scanner.snapshot --leagues nfl,cfb --days 7
"""
import argparse
import collections
import csv
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import httpx

from . import kalshi, polymarket
from .arb import evaluate, evaluate_soccer
from .config import LEAGUE_GROUPS, LEAGUES
from .matching import _tokens, match_game, match_soccer


def _same_day_candidates(kg: dict, poly_games: list[dict], tol_days: int = 0) -> list[dict]:
    """Polymarket games on (about) the same date that share at least one name word with the Kalshi game."""
    first_words = {_tokens(t["name"])[0] for t in kg["teams"] if _tokens(t["name"])}
    out = []
    for pg in poly_games:
        if abs((pg["date"] - kg["date"]).days) > tol_days:
            continue
        words = {w for t in pg["teams"] for w in _tokens(t["name"])}
        if first_words & words:
            out.append(pg)
    return out


def run_league(client, league: str, cfg: dict, days: int, min_size: float,
               today: date | None = None) -> tuple[list[dict], dict, list[str]]:
    today = today or date.today()
    window_end = today + timedelta(days=days + 1)
    stats = {"kalshi_games": 0, "outside_window": 0, "poly_games": 0, "matched": 0,
             "unmatched_no_poly_day": 0, "unmatched_names": 0, "ambiguous": 0, "no_liquidity": 0}
    rows, notes, info = [], [], []
    unmatched_shown = 0

    soccer = cfg.get("kind") == "soccer"
    tol = 1 if soccer else 0
    stats["rules_skipped"] = 0
    poly_games = polymarket.fetch_game_events(
        client, cfg["poly_series"], days=days + 1,
        parser=polymarket.parse_soccer_game if soccer else None, page=100 if soccer else 50)
    stats["poly_games"] = len(poly_games)

    to_game = kalshi.to_soccer_game if soccer else kalshi.to_game
    matcher = match_soccer if soccer else match_game
    k_markets = kalshi.fetch_series_markets(client, cfg["kalshi_series"])
    kgames = [g for ev, ms in kalshi.group_events(k_markets).items() if (g := to_game(ev, ms))]
    stats["kalshi_games"] = len(kgames)

    # Context for diagnosing matching problems: which dates does each platform have games on?
    if poly_games:
        by_date = collections.Counter(g["date"].isoformat() for g in poly_games)
        info.append("Polymarket games by date: " + ", ".join(f"{d} x{n}" for d, n in sorted(by_date.items())))
        info.append("Polymarket sample: " + "; ".join(
            " vs ".join(t["name"] for t in g["teams"]) for g in poly_games[:5]))
    k_by_date = collections.Counter(
        g["date"].isoformat() for g in kgames if today - timedelta(days=1) <= g["date"] <= window_end)
    if k_by_date:
        info.append("Kalshi games in window by date: " + ", ".join(f"{d} x{n}" for d, n in sorted(k_by_date.items())))

    for kg in kgames:
        # Kalshi lists games weeks ahead; only compare the window Polymarket was queried for
        if kg["date"] > window_end or kg["date"] < today - timedelta(days=1):
            stats["outside_window"] += 1
            continue

        res = matcher(kg, poly_games)
        if res == "ambiguous":
            stats["ambiguous"] += 1
            notes.append(f"AMBIGUOUS {kg['date']} {' vs '.join(t['name'] for t in kg['teams'])}")
            continue
        if res is None:
            same_day = [pg for pg in poly_games if abs((pg["date"] - kg["date"]).days) <= tol]
            stats["unmatched_names" if same_day else "unmatched_no_poly_day"] += 1
            if unmatched_shown < 8:
                unmatched_shown += 1
                kn = " vs ".join(t["name"] for t in kg["teams"])
                if not same_day:
                    notes.append(f"UNMATCHED {kg['date']} {kn} -> no Polymarket game on that date")
                else:
                    cands = _same_day_candidates(kg, poly_games, tol)
                    cn = "; ".join(" vs ".join(t["name"] for t in pg["teams"]) for pg in cands[:3]) \
                        or "none share a name word"
                    notes.append(f"UNMATCHED {kg['date']} {kn} -> same-day Polymarket candidates: {cn}")
            continue

        pg, mapping = res
        stats["matched"] += 1

        if soccer:
            # Both platforms must settle on 90 minutes + stoppage time, otherwise the legs are not the same bet
            if not (kg["rules_ok"] and pg["rules_ok"]):
                stats["rules_skipped"] += 1
                notes.append(f"RULES DIFFER, skipped: {' vs '.join(t['name'] for t in kg['teams'])} {kg['date']}")
                continue
            poly_quotes = {}
            for key, mk in pg["markets"].items():
                poly_quotes[key] = {"yes": polymarket.best_ask(client, mk["yes_token"]),
                                    "no": polymarket.best_ask(client, mk["no_token"])}
                time.sleep(0.1)
            opp = evaluate_soccer(kg, mapping, pg, poly_quotes, min_size=min_size)
        else:
            poly_asks = {}
            for pi, pt in enumerate(pg["teams"]):
                poly_asks[pi] = polymarket.best_ask(client, pt["token"])
                time.sleep(0.1)
            opp = evaluate(kg, mapping, pg, poly_asks, min_size=min_size)
        if opp is None:
            stats["no_liquidity"] += 1
            continue
        rows.append({
            "league": league, "date": kg["date"].isoformat(),
            "game": " vs ".join(t["name"] for t in kg["teams"]),
            "best_combo": opp.description,
            "kalshi_price": round(opp.kalshi_price, 4), "poly_price": round(opp.poly_price, 4),
            "gross_gap": round(opp.gross_gap, 4), "fees": round(opp.fees, 4),
            "net_per_contract": round(opp.net_per_contract, 4),
            "size": opp.size, "est_profit_usd": round(opp.est_profit, 2),
            "polymarket_us_slug": pg.get("us_slug") or "",
        })
    return rows, stats, info + notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="nfl,cfb",
                    help="comma list: nfl,cfb,epl,lal,... or a group: soccer (top leagues) / soccer-all")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-size", type=float, default=5.0, help="minimum contracts at the best ask on each side")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    all_rows = []
    with httpx.Client(timeout=30, headers={"User-Agent": "polymarket-kalshi-scanner/0.1"}) as client:
        requested = []
        for x in [x.strip() for x in args.leagues.split(",") if x.strip()]:
            requested.extend(LEAGUE_GROUPS.get(x, [x]))
        for league in requested:
            if league not in LEAGUES:
                print(f"unknown league {league!r}; known: {', '.join(LEAGUES)}")
                continue
            print(f"\n=== {league.upper()} ===")
            try:
                rows, st, notes = run_league(client, league, LEAGUES[league], args.days, args.min_size)
            except httpx.HTTPError as e:
                print(f"  request failed: {e}")
                continue
            print(f"  Kalshi games: {st['kalshi_games']} (outside window: {st['outside_window']}) | "
                  f"Polymarket games: {st['poly_games']} | matched: {st['matched']} | "
                  f"unmatched: {st['unmatched_no_poly_day']} no-date + {st['unmatched_names']} name | "
                  f"ambiguous: {st['ambiguous']} | rules differ: {st['rules_skipped']} | no liquidity: {st['no_liquidity']}")
            for n in notes:
                print("   ", n)
            if st["poly_games"] == 0:
                print("  (0 Polymarket games - check the series_id query; see README)")
            all_rows.extend(rows)

    all_rows.sort(key=lambda r: r["net_per_contract"], reverse=True)
    print("\nBest gaps (net of taker fees, per $1 payout contract):")
    for r in all_rows[:15]:
        print(f"  {r['net_per_contract']:+.4f}  gross {r['gross_gap']:+.4f}  size {r['size']:.0f}  "
              f"{r['league']} {r['date']} {r['game']}\n          {r['best_combo']}")
    positive = [r for r in all_rows if r["net_per_contract"] > 0]
    print(f"\n{len(all_rows)} games priced, {len(positive)} with positive net edge.")

    if all_rows:
        out = Path(args.csv) if args.csv else Path("output") / f"snapshot_{datetime.now():%Y%m%d_%H%M%S}.csv"
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
            w.writeheader()
            w.writerows(all_rows)
        print(f"Saved {out}")


if __name__ == "__main__":
    main()
