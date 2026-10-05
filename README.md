# Polymarket-Kalshi

Read-only scanner: matches upcoming sports games across Polymarket and Kalshi and reports whether a
surebet (buy "A wins" on one platform, "B wins" on the other, total cost under $1.00 after taker fees)
exists. No order placement, no dashboard, no API keys.

## Run
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m unittest discover -s tests -v        # offline tests, no network
python -m scanner.snapshot --leagues nfl,cfb --days 7
```
Results print to the console and are saved to `output/snapshot_<time>.csv` (every matched game, not just
profitable ones).

## How it works
1. Polymarket: game events for a league series (`/events?series_id=...`); each has two teams, a local
   `eventDate`, and a 2-outcome moneyline market with a `feeSchedule`. Best ask per team from the CLOB book.
2. Kalshi: `KX...GAME` series; one "X wins" market per team, grouped by event ticker (date is in the ticker).
3. Match: same game date, and each Kalshi team name must be a token-prefix of one Polymarket team name
   ("Los Angeles R" -> "Los Angeles Rams"). Ambiguous or unmatched games are counted, never guessed.
4. Price: real best asks and sizes; four combinations per game; net = 1 - cost - Kalshi fee - Polymarket fee.

## Fees (taker on both sides)
- Kalshi: `0.07 * P * (1 - P)` per contract (real fee rounds up per order).
- Polymarket: `rate * (p * (1 - p)) ** exponent`, from each market's `feeSchedule`. The docs print an extra
  leading `p`, but their own peak numbers only work without it. Verify with `/fee-rate` for thin edges.

## Known limits
- Top-of-book only (no depth walking); two-team games only; NFL + college football are the verified leagues.
- NHL/NBA/MLB Kalshi series tickers in `scanner/config.py` are guesses.
- Resolution rules differ at the edges: Kalshi resolves a postponed game at a fair price if it does not
  start within 48h, Polymarket keeps the market open. Ties pay 50/50 on both.
- Polymarket's international site is blocked for US trading; events carry a `usId` (Polymarket US slug),
  shown in the CSV, to check the same game on the US exchange.
