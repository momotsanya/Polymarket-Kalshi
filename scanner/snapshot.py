"""One-shot snapshot: match upcoming games across Polymarket and Kalshi and print the best surebet gaps.

    python -m scanner.snapshot --leagues nfl,cfb --days 7
"""
import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import kalshi, polymarket
from .arb import evaluate
from .config import LEAGUES
from .matching import match_game


def run_league(client, league: str, cfg: dict, days: int, min_size: float) -> tuple[list[dict], dict]:
    stats = {"kalshi_games": 0, "poly_games": 0, "matched": 0, "unmatched": 0, "ambiguous": 0, "no_liquidity": 0}
    rows = []

    poly_games = polymarket.fetch_game_events(client, cfg["poly_series"], days=days)
    stats["poly_games"] = len(poly_games)

    k_markets = kalshi.fetch_series_markets(client, cfg["kalshi_series"])
    kgames = [g for ev, ms in kalshi.group_events(k_markets).items() if (g := kalshi.to_game(ev, ms))]
    stats["kalshi_games"] = len(kgames)

    for kg in kgames:
        res = match_game(kg, poly_games)
        if res is None:
            stats["unmatched"] += 1
            continue
        if res == "ambiguous":
            stats["ambiguous"] += 1
            continue
        pg, mapping = res
        stats["matched"] += 1

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
    return rows, stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leagues", default="nfl,cfb")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--min-size", type=float, default=5.0, help="minimum contracts at the best ask on each side")
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    all_rows = []
    with httpx.Client(timeout=30, headers={"User-Agent": "polymarket-kalshi-scanner/0.1"}) as client:
        for league in [x.strip() for x in args.leagues.split(",") if x.strip()]:
            if league not in LEAGUES:
                print(f"unknown league {league!r}; known: {', '.join(LEAGUES)}")
                continue
            print(f"\n=== {league.upper()} ===")
            try:
                rows, st = run_league(client, league, LEAGUES[league], args.days, args.min_size)
            except httpx.HTTPError as e:
                print(f"  request failed: {e}")
                continue
            print(f"  Kalshi games: {st['kalshi_games']} | Polymarket games: {st['poly_games']} | matched: {st['matched']} "
                  f"| unmatched: {st['unmatched']} | ambiguous: {st['ambiguous']} | no liquidity: {st['no_liquidity']}")
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
