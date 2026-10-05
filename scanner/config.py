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

# Soccer (three-way: home / draw / away). Both series ids/tickers verified against the Polymarket /sports list
# and the Kalshi series list. Resolution is "90 minutes plus stoppage time" on both - checked per game.
SOCCER_LEAGUES = {
    "epl": (10188, "KXEPLGAME"), "lal": (10193, "KXLALIGAGAME"), "bun": (10194, "KXBUNDESLIGAGAME"),
    "fl1": (10195, "KXLIGUE1GAME"), "sea": (10203, "KXSERIEAGAME"), "ucl": (10204, "KXUCLGAME"),
    "uel": (10209, "KXUELGAME"), "col": (10437, "KXUECLGAME"), "mls": (10189, "KXMLSGAME"),
    "ere": (10286, "KXEREDIVISIEGAME"), "por": (10330, "KXLIGAPORTUGALGAME"), "mex": (10290, "KXLIGAMXGAME"),
    "bra": (10359, "KXBRASILEIROGAME"), "elc": (10355, "KXEFLCHAMPIONSHIPGAME"),
    "tur": (10292, "KXSUPERLIGGAME"), "scop": (10674, "KXSCOTTISHPREMGAME"),
}
for _code, (_series, _ticker) in SOCCER_LEAGUES.items():
    LEAGUES[_code] = {"poly_series": _series, "kalshi_series": _ticker, "kind": "soccer"}

# --leagues aliases
LEAGUE_GROUPS = {
    "soccer": ["epl", "lal", "bun", "fl1", "sea", "ucl", "mls"],
    "soccer-all": list(SOCCER_LEAGUES),
}

KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# Ignore quotes that are not real liquidity
MIN_PRICE = 0.02
MAX_PRICE = 0.98
