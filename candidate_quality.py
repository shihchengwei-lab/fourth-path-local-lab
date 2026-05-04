from __future__ import annotations

from collections.abc import Callable

from candidate_boundaries import (
    detect_private_prompt_logging_claim,
    detect_role_authority_claim,
    detect_role_boundary_leak,
    detect_unsupported_canon_reference,
)
from canon_checks import detect_obvious_canon_issue


RefusalDetector = Callable[[str], bool]


def main_candidate_issues(
    candidate: str,
    target_response: str | None = None,
    max_length_ratio: float | None = None,
    *,
    refusal_detector: RefusalDetector | None = None,
) -> list[str]:
    text = candidate.strip()
    lower = text.lower()
    issues: list[str] = []
    if not text:
        issues.append("empty_candidate")
    if "<|channel>thought" in lower or "<|think|>" in lower or "<think>" in lower:
        issues.append("thinking_artifact")
    if refusal_detector is not None and refusal_detector(text):
        issues.append("refusal_like")
    if detect_obvious_canon_issue(lower) is not None:
        issues.append("canon_keyword_issue")
    if detect_role_boundary_leak(lower):
        issues.append("role_boundary_leak")
    if detect_private_prompt_logging_claim(lower):
        issues.append("private_prompt_logging_claim")
    if detect_unsupported_canon_reference(lower):
        issues.append("unsupported_canon_reference")
    if detect_role_authority_claim(lower):
        issues.append("role_authority_claim")
    if target_response is not None and max_length_ratio is not None:
        target_chars = max(1, len(target_response))
        if len(text) / target_chars > max_length_ratio:
            issues.append("overlong_candidate")
    return list(dict.fromkeys(issues))
