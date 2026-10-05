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


def evaluate_soccer(kgame: dict, mapping: dict, pgame: dict, poly_quotes: dict, min_size: float = 1.0) -> Opportunity | None:
    """Three-outcome match. poly_quotes: {'team0'|'team1'|'draw': {'yes': (ask, size)|None, 'no': (ask, size)|None}}.

    Two kinds of surebet are checked, all buying at the ask as taker:
      1. Complement: YES of an outcome on one platform + NO of the SAME outcome on the other (pays $1 exactly).
      2. Cover: the cheapest YES (after fees) for each of home / draw / away (pays $1 exactly).
    Returns the best candidate, even if its net edge is negative."""
    outcomes = [(kgame["teams"][ki]["name"], kgame["teams"][ki], f"team{mapping[ki]}") for ki in (0, 1)]
    outcomes.append(("Draw", kgame["draw"], "draw"))

    best = None

    def consider(opp):
        nonlocal best
        if best is None or opp.net_per_contract > best.net_per_contract:
            best = opp

    # 1. complement per outcome
    for label, k, pkey in outcomes:
        sched = pgame["markets"][pkey]["fee_schedule"]
        pq = poly_quotes.get(pkey) or {}
        for kp, ks, klabel, pside in ((k["yes_ask"], k["yes_ask_size"], f"Kalshi YES {label}", "no"),
                                      (k["no_ask"], k["no_ask_size"], f"Kalshi NO {label}", "yes")):
            q = pq.get(pside)
            if q is None or not _ok(kp, ks, min_size) or not _ok(q[0], q[1], min_size):
                continue
            pp, ps = q
            fees = kalshi_fee(kp) + polymarket_fee(pp, sched)
            consider(Opportunity(
                description=f"{klabel} @ {kp:.2f} + Polymarket {pside.upper()} {label} @ {pp:.2f}",
                kalshi_price=kp, poly_price=pp, fees=fees,
                net_per_contract=1.0 - kp - pp - fees, size=min(ks, ps)))

    # 2. cover all three outcomes with the cheapest YES of each
    legs = []
    for label, k, pkey in outcomes:
        cands = []
        if _ok(k["yes_ask"], k["yes_ask_size"], min_size):
            cands.append((k["yes_ask"] + kalshi_fee(k["yes_ask"]), "Kalshi", k["yes_ask"], k["yes_ask_size"], label))
        q = (poly_quotes.get(pkey) or {}).get("yes")
        if q is not None and _ok(q[0], q[1], min_size):
            sched = pgame["markets"][pkey]["fee_schedule"]
            cands.append((q[0] + polymarket_fee(q[0], sched), "Polymarket", q[0], q[1], label))
        if not cands:
            legs = []
            break
        legs.append(min(cands))
    if len(legs) == 3:
        total_cost = sum(leg[0] for leg in legs)
        kp = sum(leg[2] for leg in legs if leg[1] == "Kalshi")
        pp = sum(leg[2] for leg in legs if leg[1] == "Polymarket")
        consider(Opportunity(
            description="Cover 3: " + ", ".join(f"{leg[1]} YES {leg[4]} @ {leg[2]:.2f}" for leg in legs),
            kalshi_price=kp, poly_price=pp, fees=total_cost - kp - pp,
            net_per_contract=1.0 - total_cost, size=min(leg[3] for leg in legs)))
    return best
