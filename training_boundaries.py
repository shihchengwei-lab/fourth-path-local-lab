from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from candidate_boundaries import (
    detect_private_prompt_logging_claim,
    detect_role_authority_claim,
    detect_unsupported_canon_reference,
)


CAPABILITY_DEV_AUTHORITY_FIELDS = ("prompt", "target_response")
CAPABILITY_DEV_AUTHORITY_OVERLAP_PATTERNS: tuple[tuple[str, str], ...] = (
    ("authority_label", r"\b(?:final|refusal|tool|action|audit|approval|external|safety)\s+authority\b"),
    ("approval_language", r"\bapprov(?:e|ed|al|ing)\b"),
    ("refusal_language", r"\brefus(?:e|al|ing)\b"),
    (
        "refusal_like_output",
        r"^\s*(?:i\s+(?:can't|cannot|won't|will not)|i'm unable to|sorry,\s*i\s+(?:can't|cannot)|"
        r"do not answer|refuse|i refuse)\b",
    ),
    ("verdict_language", r"\bverdict\b"),
    ("allowed_language", r"\b(?:allowed|disallowed)\b"),
    ("canon_verdict", r"\bcanon\s+(?:clause\s+)?[a-z]?\d+(?:\.\d+)*\b"),
    (
        "control_plane_prompt_reference",
        r"\b(?:hidden system prompt|system prompt|developer instructions?|private instructions?|"
        r"private prompts?|private prompt text|raw prompts?|full prompts?|full prompt content|prompt hash)\b",
    ),
    (
        "external_authority_layer",
        r"\b(?:classify|cold eyes|action gate|audit gate|safety layer|external gates?|safety gates?)\b",
    ),
    (
        "containment_layer",
        r"\bcontainment(?:\s+(?:gate|gates|check|checks|evidence|failure|failures|issue|issues|regression))?\b",
    ),
)


def capability_dev_authority_overlap_issues(row: Mapping[str, Any]) -> list[str]:
    issues: list[str] = []
    for field_name in CAPABILITY_DEV_AUTHORITY_FIELDS:
        value = row.get(field_name)
        if not isinstance(value, str) or not value.strip():
            continue
        if detect_role_authority_claim(value):
            issues.append(f"{field_name}:role_authority_claim")
        if detect_unsupported_canon_reference(value):
            issues.append(f"{field_name}:unsupported_canon_reference")
        if detect_private_prompt_logging_claim(value):
            issues.append(f"{field_name}:private_prompt_logging_claim")
        for label, pattern in CAPABILITY_DEV_AUTHORITY_OVERLAP_PATTERNS:
            if re.search(pattern, value, flags=re.IGNORECASE):
                issues.append(f"{field_name}:{label}")
    return issues
