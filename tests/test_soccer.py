"""Soccer (three-way) parsing, matching and surebet math, from saved API samples. No network."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from scanner import kalshi, polymarket, snapshot
from scanner.arb import evaluate_soccer
from scanner.matching import match_soccer, soccer_name_matches

FX = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def kalshi_events():
    return kalshi.group_events(load("kalshi_epl_game.json")["markets"])


def synthetic_arsenal_leeds(event_date_code="26OCT10"):
    """Kalshi has no Arsenal-Leeds game in the saved sample, so clone the real Leeds-Man Utd event's structure."""
    ms = copy.deepcopy(kalshi_events()["KXEPLGAME-26OCT18LEEMUN"])
    rename = {"Manchester United": "Arsenal", "Leeds United": "Leeds"}
    ev = f"KXEPLGAME-{event_date_code}ARSLEE"
    for m in ms:
        for key in ("title", "yes_sub_title", "no_sub_title"):
            for old, new in rename.items():
                m[key] = m[key].replace(old, new)
        m["event_ticker"] = ev
    g = kalshi.to_soccer_game(ev, ms)
    # Give the synthetic game prices consistent with the saved Polymarket Arsenal-Leeds quotes
    # (Arsenal 0.70/0.72, draw 0.18/0.20, Leeds 0.10/0.12) so "efficient" really is efficient.
    arsenal = next(t for t in g["teams"] if t["name"] == "Arsenal")
    leeds = next(t for t in g["teams"] if t["name"] == "Leeds")
    for q, ask in ((arsenal, 0.72), (g["draw"], 0.20), (leeds, 0.12)):
        q["yes_ask"], q["no_ask"] = ask, round(1.0 - (ask - 0.02), 2)
        q["yes_ask_size"] = q["no_ask_size"] = 500.0
    return g


class TestParsing(unittest.TestCase):
    def test_kalshi_three_way_game(self):
        g = kalshi.to_soccer_game("KXEPLGAME-26OCT19TOTCOV", kalshi_events()["KXEPLGAME-26OCT19TOTCOV"])
        self.assertEqual({t["name"] for t in g["teams"]}, {"Tottenham", "Coventry"})
        self.assertAlmostEqual(g["draw"]["yes_ask"], 0.21)
        self.assertAlmostEqual(g["draw"]["no_ask"], 0.83)
        self.assertTrue(g["rules_ok"])  # "90 minutes plus stoppage time (does not include extra time...)"
        self.assertEqual(g["date"], date(2026, 10, 19))

    def test_kalshi_two_market_event_is_rejected(self):
        ms = kalshi_events()["KXEPLGAME-26OCT19TOTCOV"][:2]
        self.assertIsNone(kalshi.to_soccer_game("KXEPLGAME-26OCT19TOTCOV", ms))

    def test_polymarket_three_way_game(self):
        pg = polymarket.parse_soccer_game(load("poly_epl_arsenal_leeds_event.json"))
        self.assertEqual(pg["date"], date(2026, 10, 10))
        self.assertEqual([t["name"] for t in pg["teams"]], ["Arsenal FC", "Leeds United FC"])
        self.assertEqual(set(pg["markets"]), {"team0", "team1", "draw"})
        toks = {t for mk in pg["markets"].values() for t in (mk["yes_token"], mk["no_token"])}
        self.assertEqual(len(toks), 6)
        self.assertEqual(pg["markets"]["draw"]["fee_schedule"]["rate"], 0.05)
        self.assertTrue(pg["rules_ok"])

    def test_polymarket_side_event_types_are_rejected(self):
        ev = load("poly_epl_arsenal_leeds_event.json")
        ev2 = copy.deepcopy(ev)
        ev2["title"] += " - Halftime Result"
        self.assertIsNone(polymarket.parse_soccer_game(ev2))
        ev3 = copy.deepcopy(ev)
        ev3["markets"][0]["sportsMarketType"] = "first_half_moneyline"
        self.assertIsNone(polymarket.parse_soccer_game(ev3))

    def test_rules_flag_when_not_90_minutes(self):
        ev = copy.deepcopy(load("poly_epl_arsenal_leeds_event.json"))
        for m in ev["markets"]:
            m["description"] = m["description"].replace("90 minutes", "the whole match")
        self.assertFalse(polymarket.parse_soccer_game(ev)["rules_ok"])


class TestNames(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(soccer_name_matches("Brighton", "Brighton & Hove Albion FC"))
        self.assertTrue(soccer_name_matches("Manchester United", "Manchester United FC"))
        self.assertTrue(soccer_name_matches("Paris Saint-Germain", "Paris Saint-Germain FC"))
        self.assertTrue(soccer_name_matches("Bayern Munich", "FC Bayern München"))

    def test_non_matches(self):
        self.assertFalse(soccer_name_matches("Manchester City", "Manchester United FC"))
        self.assertFalse(soccer_name_matches("Leeds United", "Arsenal FC"))
        self.assertFalse(soccer_name_matches("Real Madrid", "Real Sociedad"))


class TestMatchAndArb(unittest.TestCase):
    def setUp(self):
        self.pg = polymarket.parse_soccer_game(load("poly_epl_arsenal_leeds_event.json"))
        self.kg = synthetic_arsenal_leeds()

    def test_match_and_orientation(self):
        res = match_soccer(self.kg, [self.pg])
        self.assertNotIn(res, (None, "ambiguous"))
        _, mapping = res
        for ki, pi in mapping.items():
            self.assertTrue(soccer_name_matches(self.kg["teams"][ki]["name"], self.pg["teams"][pi]["name"]))

    def test_date_tolerance_is_one_day(self):
        self.assertIsNotNone(match_soccer(synthetic_arsenal_leeds("26OCT11"), [self.pg]))
        self.assertIsNone(match_soccer(synthetic_arsenal_leeds("26OCT13"), [self.pg]))

    def _quotes(self, **kw):
        base = {"team0": {"yes": (0.71, 500.0), "no": (0.30, 500.0)},
                "draw": {"yes": (0.19, 500.0), "no": (0.82, 500.0)},
                "team1": {"yes": (0.11, 500.0), "no": (0.90, 500.0)}}
        base.update(kw)
        return base

    def test_efficient_prices_are_not_a_surebet(self):
        _, mapping = match_soccer(self.kg, [self.pg])
        opp = evaluate_soccer(self.kg, mapping, self.pg, self._quotes())
        self.assertIsNotNone(opp)
        self.assertLess(opp.net_per_contract, 0)

    def test_complement_surebet_is_detected(self):
        _, mapping = match_soccer(self.kg, [self.pg])
        # Kalshi 'draw' YES ask 0.20 + Polymarket 'draw' NO at 0.60 = 0.80 gross
        quotes = self._quotes(draw={"yes": (0.19, 500.0), "no": (0.60, 500.0)})
        opp = evaluate_soccer(self.kg, mapping, self.pg, quotes)
        self.assertGreater(opp.net_per_contract, 0.05)
        self.assertIn("Draw", opp.description)

    def test_cover_all_three_surebet_is_detected(self):
        _, mapping = match_soccer(self.kg, [self.pg])
        k_home = self.kg["teams"][0]
        # Make Polymarket cheap on every outcome: 0.30 + 0.25 + 0.30 = 0.85 before fees
        quotes = {"team0": {"yes": (0.30, 500.0), "no": None},
                  "team1": {"yes": (0.30, 500.0), "no": None},
                  "draw": {"yes": (0.25, 500.0), "no": None}}
        for t in self.kg["teams"]:
            t["yes_ask"], t["no_ask"] = 0.60, None   # Kalshi expensive, no usable NO side
        self.kg["draw"]["yes_ask"], self.kg["draw"]["no_ask"] = 0.60, None
        opp = evaluate_soccer(self.kg, mapping, self.pg, quotes)
        self.assertTrue(opp.description.startswith("Cover 3"))
        self.assertGreater(opp.net_per_contract, 0.08)
        self.assertIsNotNone(k_home)

    def test_thin_books_are_ignored(self):
        _, mapping = match_soccer(self.kg, [self.pg])
        thin = {k: {"yes": (0.2, 1.0), "no": (0.2, 1.0)} for k in ("team0", "team1", "draw")}
        for t in self.kg["teams"] + [self.kg["draw"]]:
            t["yes_ask_size"] = 1.0
            t["no_ask_size"] = 1.0
        self.assertIsNone(evaluate_soccer(self.kg, mapping, self.pg, thin, min_size=5.0))


class TestRunLeagueSoccer(unittest.TestCase):
    def test_pipeline_with_patched_network(self):
        pg = polymarket.parse_soccer_game(load("poly_epl_arsenal_leeds_event.json"))
        ev_ms = [m for ms in kalshi_events().values() for m in ms]
        quotes = (0.5, 100.0)
        with mock.patch.object(polymarket, "fetch_game_events", return_value=[pg]), \
             mock.patch.object(kalshi, "fetch_series_markets", return_value=ev_ms), \
             mock.patch.object(polymarket, "best_ask", return_value=quotes):
            rows, st, notes = snapshot.run_league(
                None, "epl", {"poly_series": 1, "kalshi_series": "X", "kind": "soccer"},
                days=14, min_size=5.0, today=date(2026, 10, 9))
        self.assertEqual(st["kalshi_games"], 4)
        self.assertEqual(st["matched"], 0)   # the sample Kalshi games (Oct 18-19) are not Polymarket's (Oct 10)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
