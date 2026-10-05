"""Offline tests against saved API samples (no network). Run:  python -m unittest discover -s tests -v"""
import json
import unittest
from datetime import date
from pathlib import Path

from scanner import kalshi, polymarket
from scanner.arb import evaluate
from scanner.fees import kalshi_fee, polymarket_fee
from scanner.matching import match_game, name_matches

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


class TestFees(unittest.TestCase):
    def test_kalshi_peak_fee_is_1_75_cents_at_50c(self):
        self.assertAlmostEqual(kalshi_fee(0.5), 0.0175)

    def test_polymarket_sports_fee_matches_docs_peak(self):
        # docs: $0.75 per 100 shares at 50c with rate 0.03
        self.assertAlmostEqual(polymarket_fee(0.5, {"rate": 0.03, "exponent": 1}), 0.0075)
        self.assertAlmostEqual(polymarket_fee(0.5, {"rate": 0.05, "exponent": 1}), 0.0125)


class TestNames(unittest.TestCase):
    def test_kalshi_abbreviated_names(self):
        self.assertTrue(name_matches("Los Angeles R", "Los Angeles Rams"))
        self.assertFalse(name_matches("Los Angeles R", "Los Angeles Chargers"))
        self.assertTrue(name_matches("San Diego St.", "San Diego State Aztecs"))
        self.assertTrue(name_matches("Buffalo", "Buffalo Bills"))
        self.assertFalse(name_matches("Buffalo", "Baltimore Ravens"))


class TestKalshiParsing(unittest.TestCase):
    def test_event_date_and_game(self):
        self.assertEqual(kalshi.event_date("KXNFLGAME-26OCT12BUFLAR"), date(2026, 10, 12))
        events = kalshi.group_events(load("kalshi_nfl_game.json")["markets"])
        g = kalshi.to_game("KXNFLGAME-26OCT12BUFLAR", events["KXNFLGAME-26OCT12BUFLAR"])
        self.assertEqual({t["name"] for t in g["teams"]}, {"Los Angeles R", "Buffalo"})
        buf = next(t for t in g["teams"] if t["name"] == "Buffalo")
        self.assertAlmostEqual(buf["yes_ask"], 0.45)
        self.assertAlmostEqual(buf["no_ask"], 0.57)

    def test_college_events_group_into_two_team_games(self):
        events = kalshi.group_events(load("kalshi_cfb_game.json")["markets"])
        games = [kalshi.to_game(k, v) for k, v in events.items()]
        self.assertTrue(all(g is not None and len(g["teams"]) == 2 for g in games))


class TestPolymarketParsing(unittest.TestCase):
    def test_game_event(self):
        pg = polymarket.parse_game(load("poly_bills_rams_event.json"))
        self.assertEqual(pg["date"], date(2026, 10, 12))
        self.assertEqual([t["alias"] for t in pg["teams"]], ["Bills", "Rams"])
        self.assertEqual(pg["fee_schedule"]["rate"], 0.03)
        self.assertEqual(pg["us_slug"], "nfl-buf-lar-2026-10-12")
        self.assertNotEqual(pg["teams"][0]["token"], pg["teams"][1]["token"])


class TestMatchAndArb(unittest.TestCase):
    def setUp(self):
        events = kalshi.group_events(load("kalshi_nfl_game.json")["markets"])
        self.kg = kalshi.to_game("KXNFLGAME-26OCT12BUFLAR", events["KXNFLGAME-26OCT12BUFLAR"])
        self.pg = polymarket.parse_game(load("poly_bills_rams_event.json"))

    def test_match(self):
        res = match_game(self.kg, [self.pg])
        self.assertNotIn(res, (None, "ambiguous"))
        _, mapping = res
        k_names = [t["name"] for t in self.kg["teams"]]
        for ki, pi in mapping.items():
            self.assertTrue(name_matches(k_names[ki], self.pg["teams"][pi]["name"]))

    def test_no_match_on_different_date(self):
        other = dict(self.pg, date=date(2026, 10, 19))
        self.assertIsNone(match_game(self.kg, [other]))

    def _asks(self, mapping, bills, rams):
        # Polymarket team index 0 = Bills, 1 = Rams
        return {0: (bills, 500.0), 1: (rams, 500.0)}

    def test_sample_prices_are_not_a_surebet(self):
        # Prices from the sample files: Poly Bills ask 0.43, Rams ask ~0.58 (= 1 - Bills bid 0.42)
        _, mapping = match_game(self.kg, [self.pg])
        opp = evaluate(self.kg, mapping, self.pg, self._asks(mapping, 0.43, 0.58))
        self.assertIsNotNone(opp)
        self.assertLess(opp.net_per_contract, 0)          # gross gap ~0 and fees make it negative
        self.assertLessEqual(opp.gross_gap, 0.0001)

    def test_synthetic_surebet_is_detected(self):
        _, mapping = match_game(self.kg, [self.pg])
        # Poly Bills at 0.38 + Kalshi 'LAR YES' at 0.57 = 0.95 -> 5c gross, ~2.5c of fees
        opp = evaluate(self.kg, mapping, self.pg, self._asks(mapping, 0.38, 0.62))
        self.assertGreater(opp.net_per_contract, 0.02)
        self.assertGreater(opp.est_profit, 0)

    def test_thin_book_is_ignored(self):
        _, mapping = match_game(self.kg, [self.pg])
        asks = {0: (0.30, 1.0), 1: (0.30, 1.0)}
        self.assertIsNone(evaluate(self.kg, mapping, self.pg, asks, min_size=5.0))


if __name__ == "__main__":
    unittest.main()
