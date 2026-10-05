"""Structured matching of Kalshi games to Polymarket games: same date + both teams match by name."""
import re
import unicodedata
from datetime import timedelta
from difflib import SequenceMatcher


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


_SOCCER_STOP = {"fc", "afc", "cf", "sc", "sv", "ac", "as", "ss", "us", "fk", "bk", "cd", "ud", "rc", "rcd",
                "club", "de", "da", "do", "of", "the", "calcio", "1", "04", "05"}


def _soccer_tokens(name: str) -> list[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return [t for t in re.sub(r"[^a-z0-9 ]", " ", s).split() if t not in _SOCCER_STOP]


def soccer_name_matches(kalshi_name: str, poly_name: str) -> bool:
    """Accent/'FC'-insensitive: every Kalshi word is a prefix of some Polymarket word, or the strings are very
    similar ('Bayern Munich' ~ 'FC Bayern München'). Uniqueness within a game is enforced by the caller."""
    kt, pt = _soccer_tokens(kalshi_name), _soccer_tokens(poly_name)
    if not kt or not pt:
        return False
    if all(any(pw.startswith(kw) for pw in pt) for kw in kt):
        return True
    return SequenceMatcher(None, " ".join(kt), " ".join(pt)).ratio() >= 0.85


def match_soccer(kgame: dict, poly_games: list[dict]) -> tuple[dict, dict] | None | str:
    """Same match = date within one day (Kalshi and Polymarket can disagree on late kick-offs) and both teams match."""
    hits = []
    for pg in poly_games:
        if abs((pg["date"] - kgame["date"]).days) > 1:
            continue
        mapping = {}
        for ki, kt in enumerate(kgame["teams"]):
            cands = [pi for pi, pt in enumerate(pg["teams"]) if soccer_name_matches(kt["name"], pt["name"])]
            if len(cands) != 1:
                break
            mapping[ki] = cands[0]
        if len(mapping) == 2 and len(set(mapping.values())) == 2:
            hits.append((pg, mapping))
    if not hits:
        return None
    return hits[0] if len(hits) == 1 else "ambiguous"
