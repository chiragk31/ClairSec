"""
The matching function (METHODOLOGY.md section 3) - one implementation, used by every consumer.

A reported finding R matches a reference finding G iff
  1. R.category == G.category
  2. normalize(R.route_template) == normalize(G.route_template)
  3. R.method == G.method

Assignment is one-to-one: candidate pairs are sorted by R.confidence descending,
tie-broken by R.id ascending, and assigned greedily. An R that matches only an
already-consumed G is a *duplicate*, counted separately and excluded from FP.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


def _segments(path: str) -> list[str]:
    return [s for s in path.strip().strip("/").split("/") if s != ""]


def normalize(route: str, route_table: Iterable[str] | None = None) -> str:
    """
    Replace concrete path segments matched by the target's route table with the
    table's placeholders, lowercase, and strip trailing slashes.
    """
    clean = "/" + "/".join(_segments(route or "/"))
    if route_table and "{" not in clean:
        concrete = _segments(clean)
        for template in sorted(set(route_table)):
            tsegs = _segments(template)
            if len(tsegs) != len(concrete):
                continue
            if all(t == c or (t.startswith("{") and t.endswith("}")) for t, c in zip(tsegs, concrete)):
                clean = "/" + "/".join(tsegs)
                break
    return clean.lower()


def _get(f: Any, key: str, default: Any = None) -> Any:
    if isinstance(f, dict):
        return f.get(key, default)
    return getattr(f, key, default)


def _confidence(f: Any) -> float:
    c = _get(f, "confidence")
    if isinstance(c, (int, float)):
        return float(c)
    if isinstance(c, dict):
        return float(c.get("score") or 0.0)
    score = getattr(c, "score", None)
    return float(score) if score is not None else 0.0


def _key(f: Any, route_table: Iterable[str] | None) -> tuple[str, str, str]:
    category = _get(f, "category") or ""
    category = getattr(category, "value", category)
    return (
        str(category).upper(),
        normalize(_get(f, "route_template") or "", route_table),
        str(_get(f, "method") or "").upper(),
    )


@dataclass
class MatchResult:
    pairs: list[tuple[Any, Any]] = field(default_factory=list)   # (R, G) true positives
    false_positives: list[Any] = field(default_factory=list)     # unmatched R
    false_negatives: list[Any] = field(default_factory=list)     # unmatched G
    duplicates: list[Any] = field(default_factory=list)          # R matching a consumed G

    @property
    def tp(self) -> int:
        return len(self.pairs)

    @property
    def fp(self) -> int:
        return len(self.false_positives)

    @property
    def fn(self) -> int:
        return len(self.false_negatives)

    @property
    def detection_rate(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    @property
    def fdr(self) -> float | None:
        denom = self.tp + self.fp
        return self.fp / denom if denom else None


def match_findings(
    reported: list[Any],
    reference: list[Any],
    route_table: Iterable[str] | None = None,
) -> MatchResult:
    table = list(route_table) if route_table else None
    ordered = sorted(reported, key=lambda r: (-_confidence(r), str(_get(r, "id") or "")))
    ref_keys = [_key(g, table) for g in reference]
    consumed = [False] * len(reference)
    result = MatchResult()
    for r in ordered:
        rk = _key(r, table)
        free = next((i for i, gk in enumerate(ref_keys) if gk == rk and not consumed[i]), None)
        if free is not None:
            consumed[free] = True
            result.pairs.append((r, reference[free]))
        elif rk in ref_keys:
            result.duplicates.append(r)
        else:
            result.false_positives.append(r)
    result.false_negatives = [g for i, g in enumerate(reference) if not consumed[i]]
    return result


def diff_scans(base: list[Any], head: list[Any], route_table: Iterable[str] | None = None) -> dict[str, list[Any]]:
    """
    Regression watch (FEATURES.md F13), built on the same matching function.

    base/head are the *confirmed* findings of two scans of the same project.
    Base findings carry ``verification_outcome`` when known.
    """
    m = match_findings(head, base, route_table)
    still_open, came_back = [], []
    for head_f, base_f in m.pairs:
        outcome = _get(base_f, "verification_outcome")
        outcome = str(getattr(outcome, "value", outcome) or "").lower()
        (came_back if outcome == "fixed" else still_open).append(head_f)
    return {
        "new": m.false_positives,
        "still_open": still_open + m.duplicates,
        "came_back": came_back,
        "fixed_since_last_scan": m.false_negatives,
    }
