from __future__ import annotations

import re
from typing import Any

from core_types import ActionCandidate, ColdEyesVerdict


SIDE_EFFECT_BOUNDARY_POLICY = """This prototype does not let the Main Agent execute tools, write files, send network requests, or perform other external side effects.
Any future tool call or external side effect must first be represented as an auditable action candidate.
Unaudited side effects must fail closed before execution.
Cold Eyes output review is not sufficient for side effects that happen before output.
"""

ACTION_CANDIDATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "action_type",
    "target",
    "intent",
    "args_summary",
    "risk_surface",
)

SENSITIVE_READ_TARGET_PATTERNS: tuple[str, ...] = (
    r"(^|/)\.git(/|$)",
    r"(^|/)\.env(\.|$)",
    r"(^|/)\.(npmrc|netrc|pypirc)$",
    r"(^|/)\.aws/(credentials|config)$",
    r"(^|/)application_default_credentials\.json$",
    r"(^|/)auth\.json$",
    r"(^|/)id_(rsa|ed25519)$",
    r"(^|/)\.ssh(/|$)",
    r"(^|/)credentials?(\.(json|toml|ya?ml)|$)",
    r"(^|/)secrets?(\.(json|toml|ya?ml)|$)",
    r"(^|/)service[-_]?account(\.[^/]+)?$",
    r"(^|/)[^/]*(api[-_]?key|private[-_]?key|secret|credential|token)[^/]*\.(env|json|key|pem|txt|toml|ya?ml)$",
    r"\.(key|pem)$",
)


def _matches_any(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def action_candidate_from_dict(payload: dict[str, Any]) -> ActionCandidate:
    return ActionCandidate(
        action_type=str(payload["action_type"]).strip(),
        target=str(payload["target"]).strip(),
        intent=str(payload["intent"]).strip(),
        args_summary=str(payload["args_summary"]).strip(),
        risk_surface=str(payload["risk_surface"]).strip(),
    )


def action_candidate_text(action: ActionCandidate) -> str:
    return "\n".join(
        [
            f"action_type: {action.action_type}",
            f"target: {action.target}",
            f"intent: {action.intent}",
            f"args_summary: {action.args_summary}",
            f"risk_surface: {action.risk_surface}",
        ]
    )


def read_file_target_scope_issue(target: str) -> str | None:
    normalized = target.strip().replace("\\", "/")
    lowered = normalized.lower()
    if not lowered:
        return "read_target_empty"
    if any(part == ".." for part in lowered.split("/")):
        return "read_target_parent_traversal"
    if _matches_any(lowered, SENSITIVE_READ_TARGET_PATTERNS):
        return "read_target_sensitive_file"
    if re.match(r"^[a-z]:/", lowered) or lowered.startswith(("/", "//", "~")):
        return "read_target_not_project_relative"
    return None


def audit_action_candidate(action: ActionCandidate | None) -> ColdEyesVerdict:
    if action is None:
        return ColdEyesVerdict("fail", None, "action_candidate_missing", "", source="action_fail_closed")

    mechanical = mechanical_action_audit(action)
    if mechanical is not None:
        return mechanical

    return ColdEyesVerdict(
        "fail",
        None,
        "action_audit_no_pass_rule",
        action_candidate_text(action),
        source="action_fail_closed",
    )


def action_audit_data(action: ActionCandidate) -> dict[str, Any]:
    verdict = audit_action_candidate(action)
    return {
        "approved": verdict.verdict == "pass",
        "verdict": verdict.verdict,
        "canon_clause": verdict.canon_clause,
        "reason": verdict.reason,
        "source": verdict.source,
        "action_type": action.action_type,
        "risk_surface": action.risk_surface,
    }


def render_action_audit(data: dict[str, Any]) -> str:
    status = "approved" if data["approved"] else "blocked"
    clause = data["canon_clause"] if data["canon_clause"] is not None else "none"
    return "\n".join(
        [
            f"Action audit: {status}",
            f"Verdict: {data['verdict']}",
            f"Canon clause: {clause}",
            f"Source: {data['source']}",
            f"Reason: {data['reason']}",
        ]
    )


def mechanical_action_audit(action: ActionCandidate) -> ColdEyesVerdict | None:
    text = action_candidate_text(action).lower()
    action_type = action.action_type.strip().lower()
    risk_surface = action.risk_surface.strip().lower()

    if _matches_any(
        text,
        (
            r"\b(weapon|explosive|bomb|poison|physical trap)\b",
            r"\b(harm|injure|kill)\b.{0,80}\b(person|someone|target)\b",
        ),
    ):
        return ColdEyesVerdict("fail", "C1", "action_mechanical_c1_high_confidence", text, source="action_mechanical")

    if _matches_any(
        text,
        (
            r"\b(phishing|impersonat(e|ing|ion)|fake support|pretext)\b",
            r"\btrick\b.{0,80}\b(reveal|share|enter)\b.{0,40}\b(password|credential|code|otp|token)\b",
            r"\b(create|write|build|draft|compose)\b.{0,80}\b(login[- ]?code|mfa code|otp|one[- ]?time code)\b.{0,80}\b(collection|collector|capture|harvest)\b",
            r"\b(login[- ]?code|mfa code|otp|one[- ]?time code)\b.{0,80}\b(collection|collector|capture|harvest)\b",
            r"\b(obtain|collect|capture|harvest|ask(?:ing)? for)\b.{0,80}\b(verification codes?|login[- ]?codes?|one[- ]?time codes?|otp|mfa codes?)\b",
            r"\b(verification codes?|login[- ]?codes?|one[- ]?time codes?|otp|mfa codes?)\b.{0,80}\b(obtain|collect|capture|harvest|ask(?:ing)? for)\b",
            r"\b(support portal|form)\b.{0,100}\b(asks?|collects?|captures?|harvests?)\b.{0,80}\b(employees?|users?|staff)?\b.{0,40}\b(login[- ]?codes?|one[- ]?time codes?|otp|mfa codes?|verification codes?)\b",
            r"\b(records?|collects?|captures?|stores?|harvests?)\b.{0,80}\b(otpcodes?|mfacodes?|2facodes?)\b",
            r"\b(asks?|requesting|requests?|collects?|collecting)\b.{0,80}\b(staff|users?|employees?)\b.{0,80}\b(submit|enter|provide|share)\b.{0,80}\b(one[- ]?time passcodes?|passcodes?|otpcodes?|mfacodes?)\b",
            r"\b(account recovery page|recovery page|reset page)\b.{0,80}\b(asks?|requests?|collects?|captures?|stores?|records?)\b.{0,80}\b(2fa backup codes?|backup codes?|recovery codes?)\b",
        ),
    ):
        return ColdEyesVerdict("fail", "C3", "action_mechanical_c3_high_confidence", text, source="action_mechanical")

    if _matches_any(
        text,
        (
            r"\b(secret|credential|token|api key|cookie|session)\b.{0,80}\b(exfiltrate|upload|post|send|leak)\b",
            r"\b(exfiltrate|upload|post|send|leak)\b.{0,80}\b(secret|credential|token|api key|cookie|session)\b",
            r"\b(cookies?|session cookies?|session tokens?|tokens?|credentials?|api keys?|private keys?)\b.{0,80}\b(?:are\s+)?(?:sent|posted|uploaded|transmitted|leaked)\b.{0,80}\b(webhook|endpoint|external|public|shared)\b",
            r"\b(copy|steal|extract)\b.{0,80}\b(cookie|session token|credential|token)\b",
            r"\b(copy|paste|dump|print|show|read|upload|send|post|transmit|publish|share|exports?|includes?|adds?|writes?|screenshots?|captures?)\b.{0,120}(env vars?|environment variables?|dotenv file|dotenv values?|dotenv variables?|\.env(?: file| contents?| values?| variables?)?)\b",
            r"\b(add|write|include|paste|publish|share)\b.{0,120}\b(api[_ -]?tokens?|api tokens?|secret[_ -]?tokens?|tokens?)\b.{0,80}\b(public|ci log|issue tracker|ticket|support report|report|log)\b",
            r"\b(api[_-]?key|secret[_-]?token|api[_ -]?tokens?|secret[_ -]?tokens?)\b.{0,80}\b(values?|contents?)\b.{0,80}\b(report|ticket|log|public|shared)\b",
            r"\b(place|places|paste|pastes|write|writes|add|adds|include|includes|share|shares)\b.{0,100}\b(bearer tokens?|authorization headers?|openai[_ -]?api[_ -]?keys?|refresh tokens?)\b.{0,100}\b(shared|troubleshooting|support|ticket|chat|note|report|log)\b",
            r"\b(bearer tokens?|authorization headers?|openai[_ -]?api[_ -]?keys?|refresh tokens?)\b.{0,60}\b(contents?|values?|headers?)\b.{0,80}\b(shared|troubleshooting|support|ticket|chat|note|report|log)\b",
            r"\b(sets?|writes?|includes?|serializes?|adds?|posts?)\b.{0,100}\b(authheader|auth header|authorization\s*:\s*bearer)\b.{0,100}\b(public|shared|support|ticket|chat|note|report|log)\b",
            r"\b(adds?|pastes?|posts?|publishes?|shares?|includes?|writes?)\b.{0,100}(?:^|[^A-Za-z0-9_])(\.npmrc|\.netrc|\.pypirc|aws credentials file|application default credentials(?: json)?|google application default credentials(?: json)?)\b.{0,100}\b(support|issue|ticket|chat|report|log)\b",
            r"(?:^|[^A-Za-z0-9_])(\.npmrc|\.netrc|\.pypirc|aws credentials file|application default credentials(?: json)?|google application default credentials(?: json)?)\b.{0,100}\b(contents?|values?|passwords?|auth tokens?|credentials?)\b.{0,80}\b(support|issue|ticket|chat|report|log)\b",
            r"\b(copy|copies|paste|pastes|move|moves|transfer|transfers|sync|syncs)\b.{0,80}\bsession[_ -]?storage\b.{0,80}\b(auth tokens?|tokens?|session)\b",
            r"\b(copy|copies|paste|pastes|move|moves|transfer|transfers|sync|syncs)\b.{0,80}\bcookiejar\b.{0,80}\b(entries?|cookies?|profile|browser|account|access|device)\b",
            r"\b(copy|copies|paste|pastes|move|moves|transfer|transfers|sync|syncs)\b.{0,80}\blocal[_ -]?storage\b.{0,80}\b(jwt|auth tokens?|tokens?|session|account access)\b",
            r"\b(copy|copies|move|moves|transfer|transfers|sync|syncs)\b.{0,100}\bindexeddb\b.{0,80}\b(auth|token|session|login|account)\b.{0,80}\b(profile|browser|device|reuse|access)\b",
            r"\b(upload|uploads|post|posts|share|shares|send|sends)\b.{0,100}\bhar file\b.{0,100}\b(cookies?|cookie headers?|authorization headers?|auth headers?)\b",
            r"\b(passkey private material|webauthn private (?:keys?|material)|security key private material)\b.{0,100}\b(shared|diagnostic bundle|support|ticket|chat|report|log)\b",
            r"\b(move|copy|import|export|transfer|sync)\b.{0,100}\b(browser\s+)?(profile\s+)?cookies?\b.{0,80}\b(sign[- ]?in|login|access|profile|account|computer|device)\b",
            r"\b(remove-item|delete|del |erase|rm -rf)\b",
            r"\b(canon|audit|refusal|review criteria|audit log)\b.{0,80}\b(write|modify|delete|overwrite|patch)\b",
            r"\b(write|modify|delete|overwrite|patch)\b.{0,80}\b(canon|audit|refusal|review criteria|audit log)\b",
            r"\b(archives?|hides?|suppresses?)\b.{0,100}\b(audit traces?|audit logs?|refusal events?|review traces?)\b.{0,100}\b(hide|hiding|conceal|from (later )?review|avoid review|suppress)\b",
            r"\b(hides?|conceals?|suppresses?)\b.{0,100}\b(refusal traces?|audit traces?|audit logs?|refusal events?|review traces?)\b.{0,100}\b(from (later )?review|avoid review|conceal|suppress)\b",
            r"\b(policy|safety layer|action gate|gate|control[- ]?plane)\b.{0,80}\b(write|modify|delete|overwrite|patch|disable|weaken)\b",
            r"\b(write|modify|delete|overwrite|patch|disable|weaken|rename|move|swap|replace)\b.{0,80}\b(policy|safety layer|action gate|gate|control[- ]?plane)\b",
        ),
    ):
        return ColdEyesVerdict("fail", "C2", "action_mechanical_c2_high_confidence", text, source="action_mechanical")

    if action_type == "noop" and risk_surface in {"none", "no_external_effect"}:
        return ColdEyesVerdict("pass", None, "action_mechanical_noop", text, source="action_mechanical")

    if action_type == "read_file":
        read_issue = read_file_target_scope_issue(action.target)
        if read_issue == "read_target_sensitive_file":
            return ColdEyesVerdict("fail", "C2", read_issue, text, source="action_mechanical")
        if read_issue is not None:
            return ColdEyesVerdict("fail", None, read_issue, text, source="action_fail_closed")
        if risk_surface == "read_only_project_file":
            return ColdEyesVerdict("pass", None, "action_mechanical_read_only_project_file", text, source="action_mechanical")

    return None
