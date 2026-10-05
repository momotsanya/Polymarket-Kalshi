"""Structured matching of Kalshi games to Polymarket games: same date + both teams match by name."""
import re


def _tokens(name: str) -> list[str]:
    return re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()


def name_matches(kalshi_name: str, poly_full_name: str) -> bool:
    """Every Kalshi token must be a prefix of the corresponding Polymarket token, in order.
    'Los Angeles R' -> 'Los Angeles Rams', 'San Diego St.' -> 'San Diego State Aztecs', 'Buffalo' -> 'Buffalo Bills'.
    """
    kt, pt = _tokens(kalshi_name), _tokens(poly_full_name)
    if not kt or len(kt) > len(pt):
        return False
    return all(p.startswith(k) for k, p in zip(kt, pt))


def match_game(kgame: dict, poly_games: list[dict]) -> tuple[dict, dict] | None | str:
    """Returns (poly_game, {kalshi_index: poly_team_index}), None if no match, or 'ambiguous'."""
    hits = []
    for pg in poly_games:
        if pg["date"] != kgame["date"]:
            continue
        mapping = {}
        for ki, kt in enumerate(kgame["teams"]):
            cands = [pi for pi, pt in enumerate(pg["teams"]) if name_matches(kt["name"], pt["name"])]
            if len(cands) != 1:
                break
            mapping[ki] = cands[0]
        if len(mapping) == 2 and len(set(mapping.values())) == 2:
            hits.append((pg, mapping))
    if not hits:
        return None
    return hits[0] if len(hits) == 1 else "ambiguous"
