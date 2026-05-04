from __future__ import annotations

import re
from typing import Any

from canon_patterns import (
    DEFENSIVE_CONTEXT_PATTERNS,
    INPUT_CANON_PATTERNS,
    MECHANICAL_CANON_PATTERNS,
)

DEFENSIVE_BROAD_C3_PATTERN_IDS = frozenset({"C3-p1", "C3-p5"})


def matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.DOTALL) for pattern in patterns)


def is_defensive_context(text: str) -> bool:
    return matches_any(text.lower(), DEFENSIVE_CONTEXT_PATTERNS)


def detect_obvious_canon_issue(text: str) -> str | None:
    lower = text.lower()
    if is_defensive_context(lower):
        return None

    for clause, patterns in INPUT_CANON_PATTERNS:
        if matches_any(lower, patterns):
            return clause
    return None


def mechanical_policy_result_is_defensive_false_positive(audit_result: Any, text: str) -> bool:
    if not audit_result.matches:
        return False
    if not is_defensive_context(text):
        return False
    return all(
        match.rule_id == "C3" and match.pattern_id in DEFENSIVE_BROAD_C3_PATTERN_IDS
        for match in audit_result.matches
    )


def mechanical_high_confidence_clause(candidate: str) -> str | None:
    lower = candidate.strip().lower()
    if not lower:
        return None

    for clause, patterns in MECHANICAL_CANON_PATTERNS:
        if matches_any(lower, patterns):
            return clause
    return None
