"""Surebet check on a matched game, using real buy (ask) prices on both sides and taker fees.

For a two-way game, owning 'A wins' on one platform and 'B wins' on the other pays $1.00 whoever wins
(a tie pays 0.50 + 0.50 on both platforms for the NFL). It is a surebet when the total cost, including
fees, is under $1.00.
"""
from dataclasses import dataclass

from .config import MAX_PRICE, MIN_PRICE
from .fees import kalshi_fee, polymarket_fee


@dataclass
class Opportunity:
    description: str
    kalshi_price: float
    poly_price: float
    fees: float
    net_per_contract: float
    size: float

    @property
    def gross_gap(self) -> float:
        return 1.0 - self.kalshi_price - self.poly_price

    @property
    def est_profit(self) -> float:
        return self.net_per_contract * self.size


def _ok(price, size, min_size) -> bool:
    return price is not None and size is not None and MIN_PRICE <= price <= MAX_PRICE and size >= min_size


def evaluate(kgame: dict, mapping: dict, pgame: dict, poly_asks: dict, min_size: float = 1.0) -> Opportunity | None:
    """poly_asks: {poly_team_index: (ask_price, ask_size) or None}. Returns the best combination
    (even if its net edge is negative) or None if no combination has real liquidity on both sides."""
    ka, kb = kgame["teams"]
    pa_idx, pb_idx = mapping[0], mapping[1]

    # Ways to buy exposure to "team X wins" on Kalshi: YES of X, or NO of the other team
    kalshi_a = [(ka["yes_ask"], ka["yes_ask_size"], f"Kalshi YES {ka['name']}"),
                (kb["no_ask"], kb["no_ask_size"], f"Kalshi NO {kb['name']}")]
    kalshi_b = [(kb["yes_ask"], kb["yes_ask_size"], f"Kalshi YES {kb['name']}"),
                (ka["no_ask"], ka["no_ask_size"], f"Kalshi NO {ka['name']}")]

    best = None
    # Kalshi covers A, Polymarket covers B (and vice versa)
    for k_options, p_idx in ((kalshi_a, pb_idx), (kalshi_b, pa_idx)):
        pq = poly_asks.get(p_idx)
        if pq is None:
            continue
        p_price, p_size = pq
        if not _ok(p_price, p_size, min_size):
            continue
        for k_price, k_size, k_label in k_options:
            if not _ok(k_price, k_size, min_size):
                continue
            fees = kalshi_fee(k_price) + polymarket_fee(p_price, pgame["fee_schedule"])
            net = 1.0 - k_price - p_price - fees
            opp = Opportunity(
                description=f"{k_label} @ {k_price:.2f} + Polymarket {pgame['teams'][p_idx]['name']} @ {p_price:.2f}",
                kalshi_price=k_price, poly_price=p_price, fees=fees,
                net_per_contract=net, size=min(k_size, p_size),
            )
            if best is None or opp.net_per_contract > best.net_per_contract:
                best = opp
    return best
