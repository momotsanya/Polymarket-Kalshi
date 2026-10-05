"""League configuration: Polymarket series id + Kalshi series ticker for game-winner markets.

Verified from sample data: nfl and cfb (Polymarket series ids from /sports; Kalshi
KXNFLGAME / KXNCAAFGAME). The NHL/NBA/MLB Kalshi tickers below are GUESSES by analogy -
if a league returns zero Kalshi events, check the ticker on kalshi.com and fix it here.
"""

LEAGUES = {
    "nfl": {"poly_series": 12185, "kalshi_series": "KXNFLGAME"},
    "cfb": {"poly_series": 12756, "kalshi_series": "KXNCAAFGAME"},
    "nhl": {"poly_series": 10346, "kalshi_series": "KXNHLGAME"},   # Kalshi ticker unverified
    "nba": {"poly_series": 10345, "kalshi_series": "KXNBAGAME"},   # Kalshi ticker unverified
    "mlb": {"poly_series": 3,     "kalshi_series": "KXMLBGAME"},   # Kalshi ticker unverified
}

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# Ignore quotes that are not real liquidity
MIN_PRICE = 0.02
MAX_PRICE = 0.98
