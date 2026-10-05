"""Taker fee models (per contract, in dollars). We always assume we are the TAKER on both sides.

Kalshi:      fee = ceil_to_cent(0.07 * C * P * (1 - P))  -> modelled here without the per-order rounding.
Polymarket:  fee = C * rate * (p * (1 - p)) ** exponent, rate/exponent from the market's own
             `feeSchedule` (takerOnly). Polymarket's docs print the formula with an extra leading `p`,
             but their own peak-fee figures ($0.75 per 100 shares at rate 0.03, 50c) only work
             WITHOUT it, so that is what is used here. Cross-check with
             GET https://clob.polymarket.com/fee-rate?token_id=... before trusting a thin edge.
"""

KALSHI_FEE_RATE = 0.07


def kalshi_fee(price: float, rate: float = KALSHI_FEE_RATE) -> float:
    return rate * price * (1.0 - price)


def polymarket_fee(price: float, schedule: dict | None) -> float:
    if not schedule:
        return 0.0
    rate = float(schedule.get("rate", 0.0))
    exponent = float(schedule.get("exponent", 1.0))
    return rate * (price * (1.0 - price)) ** exponent
