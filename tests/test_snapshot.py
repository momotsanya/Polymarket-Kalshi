"""run_league with the network patched out (saved samples only)."""
import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scanner import kalshi, polymarket, snapshot

FX = Path(__file__).parent / "fixtures"


class TestRunLeague(unittest.TestCase):
    def test_counts_and_reasons(self):
        k_markets = json.loads((FX / "kalshi_nfl_game.json").read_text(encoding="utf-8"))["markets"]
        pg = polymarket.parse_game(json.loads((FX / "poly_bills_rams_event.json").read_text(encoding="utf-8")))
        with mock.patch.object(polymarket, "fetch_game_events", return_value=[pg]), \
             mock.patch.object(kalshi, "fetch_series_markets", return_value=k_markets), \
             mock.patch.object(polymarket, "best_ask", return_value=(0.60, 100.0)):
            rows, st, notes = snapshot.run_league(
                None, "nfl", {"poly_series": 1, "kalshi_series": "X"}, days=7, min_size=5.0,
                today=date(2026, 10, 7))
        # BUF-LAR (Oct 12) matches; BAL-ATL and CHI-GB (Oct 11) have no Polymarket game that day
        self.assertEqual(st["kalshi_games"], 3)
        self.assertEqual(st["matched"], 1)
        self.assertEqual(st["unmatched_no_poly_day"], 2)
        self.assertEqual(len(rows), 1)
        self.assertTrue(any("no Polymarket game on that date" in n for n in notes))

    def test_games_beyond_window_are_not_counted_as_unmatched(self):
        k_markets = json.loads((FX / "kalshi_nfl_game.json").read_text(encoding="utf-8"))["markets"]
        with mock.patch.object(polymarket, "fetch_game_events", return_value=[]), \
             mock.patch.object(kalshi, "fetch_series_markets", return_value=k_markets):
            _, st, _ = snapshot.run_league(None, "nfl", {"poly_series": 1, "kalshi_series": "X"},
                                           days=2, min_size=5.0, today=date(2026, 10, 1))
        self.assertEqual(st["outside_window"], 3)
        self.assertEqual(st["unmatched_no_poly_day"], 0)


if __name__ == "__main__":
    unittest.main()
