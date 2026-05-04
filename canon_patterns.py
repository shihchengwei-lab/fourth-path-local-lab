from __future__ import annotations

"""Pattern data for deterministic canon checks.

This module owns regex data only. Callers still own routing, verdict semantics,
audit logging, retries, and refusal behavior.
"""

DEFENSIVE_CONTEXT_PATTERNS: tuple[str, ...] = (
    r"\b(documented account recovery|verify ownership|rotate exposed|revok(e|ing) exposed)\b",
    r"\b(review account login history|checking access logs|check access logs)\b",
    r"\b(verify|check|confirm)\b.{0,80}\b(sender|domain|email)\b.{0,80}\b(password reset|official|support)\b",
    r"\bpassword reset email\b.{0,80}\b(official|support|directly|avoid clicking)\b",
    r"\bspoofed email\b.{0,80}\b(signs|typos|suspicious)\b",
    r"\b(common signs of phishing|signs of phishing|phishing warning signs|anti-phishing|report suspicious|report suspected)\b",
    r"\b(safe signals|signals)\b.{0,80}\bphishing emails?\b",
    r"\b(indicators|red flags|warning signs|signs)\b.{0,80}\bphishing emails?\b",
    r"\bphishing emails?\b.{0,80}\b(often|usually|may|commonly)\b.{0,80}\b(urgent|suspicious|mismatched|generic greetings|unusual attachments|sensitive information|passwords?|one-time codes?)\b",
    r"\bphishing\b.{0,80}\b(awareness training|employee training|red flags|warning signs|suspicious sender)\b",
    r"\breport (the )?(phishing attempt|suspected phishing)\b",
    r"\b(phishing awareness|employee awareness training)\b",
    r"\b(social engineering warning signs|social engineering awareness)\b",
    r"\b(verify sender identity|defensive account security|security awareness)\b",
    r"\b(possible|suspected|reported)\b.{0,40}\baccount impersonation\b",
    r"\b(account impersonation)\b.{0,80}\b(verify|trusted channel|without accusing|premature accusation)\b",
    r"\b(enable multi-factor authentication|configure application logging|avoiding secrets)\b",
    r"(辨識|識別).{0,30}(釣魚|仿冒).{0,30}(訊息|郵件|信件)",
    r"(回報|通報).{0,30}(可疑|釣魚|仿冒).{0,30}(訊息|郵件|信件|事件)",
    r"(正式|官方).{0,20}(帳號復原|復原流程)",
    r"(避免|不要).{0,30}(密碼|權杖|金鑰|秘密).{0,30}(日誌|紀錄)",
)

INPUT_CANON_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "C2",
        (
            r"\bbypass\b.{0,80}\b(password|login|auth|authentication|security|permission|monitoring)\b",
            r"\bdisable\b.{0,80}\b(windows defender|antivirus|edr|logging|monitoring)\b",
            r"\bsteal\b.{0,80}\b(cookie|token|credential|password|session)\b",
            r"\bextract\b.{0,80}\b(password|credential|token|cookie)\b",
            r"\b(copy|paste|dump|print|show|read|upload|send|post|transmit|publish|share)\b.{0,120}\b(environment variables?|dotenv file|dotenv values?|dotenv variables?|\.env(?: file| contents?| values?| variables?)?)\b",
            r"\b(move|copy|import|export|transfer|sync)\b.{0,100}\b(browser\s+)?(profile\s+)?cookies?\b.{0,80}\b(sign[- ]?in|login|access|profile|account|computer|device)\b",
            r"(搬|移|同步|匯入|轉移|複製).{0,30}(瀏覽器)?\s*cookie.{0,30}(登入|帳號|另一台|電腦|裝置)",
            r"(瀏覽器)?\s*cookie.{0,30}(搬|移|同步|匯入|轉移|複製).{0,30}(登入|帳號|另一台|電腦|裝置)",
            r"\b(reveal|show|print|dump|quote)\b.{0,120}\b(hidden system|developer instructions?|audit instructions?|private audit|control[- ]?plane)\b",
            r"\b(hidden system|developer instructions?|audit instructions?|private audit)\b.{0,120}\b(avoid|bypass|evade|circumvent)\b.{0,60}\b(gate|audit|review|safety layer)\b",
            r"\bmimikatz\b",
            r"\bprivilege escalation\b",
            r"(繞過|規避|破解|跳過).{0,30}(登入|密碼|驗證|認證|安全|權限|監控|日誌)",
            r"(取得|竊取|偷取|擷取).{0,30}(密碼|憑證|權杖|token|cookie|session)",
            r"(關閉|停用|禁用).{0,30}(防毒|監控|日誌|紀錄|安全系統)",
        ),
    ),
    (
        "C3",
        (
            r"\bphishing\b.{0,80}\b(email|message|page|campaign|site|password|credential|otp|code)\b",
            r"\bfake login\b",
            r"\bimpersonat(e|ion|ing)\b.{0,80}\b(account|user|employee|bank|support|payroll)\b",
            r"\bspoof\b.{0,80}\b(email|caller|identity|login)\b",
            r"\b(login[- ]?code|mfa code|otp|one[- ]?time code)\b.{0,80}\b(collection|collector|capture|harvest)\b",
            r"\b(support portal|form)\b.{0,100}\b(asks?|collects?|captures?|harvests?)\b.{0,80}\b(employees?|users?|staff)?\b.{0,40}\b(login[- ]?codes?|one[- ]?time codes?|otp|mfa codes?|verification codes?)\b",
            r"\bfake\b.{0,40}\b(payroll|invoice)\b.{0,80}\b(email|message)\b.{0,100}\b(asks?|steal|capture|collect|enter|password|credential|one[- ]?time|otp|login code)\b",
            r"(釣魚|假登入|偽造登入|冒充|冒名|仿冒).{0,80}(密碼|憑證|驗證碼|一次性|權杖|帳號)",
        ),
    ),
    (
        "C1",
        (
            r"\bmake\b.{0,80}\b(explosive|bomb|poison)\b",
            r"\bconstruct(?:ing)?\b.{0,80}\b(weapon|explosive|bomb|trap)\b",
            r"\bweapon\b.{0,80}\b(instruction|build|assemble)\b",
            r"\bkill\b.{0,80}\b(step|method|guide|instructions)\b",
            r"\b(improvised explosive device|ied)\b",
            r"\bharmful recipe\b.{0,80}\b(explosive|poison|weapon)\b",
            r"(製作|組裝).{0,30}(爆裂物|炸彈|毒物|武器)",
        ),
    ),
)

MECHANICAL_CANON_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "C3",
        (
            r"\b(fake|spoofed|forged)\b.{0,40}\b(login|password reset|reset flow|signin|sign-in)\b",
            r"\b(login|password reset|reset flow|signin|sign-in)\b.{0,80}\b(collect|capture|harvest|obtain|steal)\b.{0,40}\b(password|credential|code|otp|mfa|token)\b",
            r"\b(writ(?:e|es|ing)|draft(?:s|ing)?|craft(?:s|ing)?|create(?:s|ing)?|compose(?:s|ing)?)\b.{0,50}\b(phishing|pretext|fake support)\b.{0,50}\b(email|message|call|script|campaign)\b",
            r"\b(phishing|pretext|pretext call|fake support|impersonat(e|ing|ion))\b.{0,80}\b(collect|capture|harvest|obtain|steal|trick)\b.{0,50}\b(passwords?|credentials?|codes?|otp|mfa|tokens?|private account details|account details)\b",
            r"\btrick\b.{0,80}\b(reveal|provide|enter|share)\b.{0,40}\b(password|credential|one-time|otp|mfa|code)\b",
            r"\b(create|write|build|draft|compose)\b.{0,80}\b(login[- ]?code|mfa code|otp|one[- ]?time code)\b.{0,80}\b(collection|collector|capture|harvest)\b",
            r"\b(login[- ]?code|mfa code|otp|one[- ]?time code)\b.{0,80}\b(collection|collector|capture|harvest)\b",
            r"\b(support portal|form)\b.{0,100}\b(asks?|collects?|captures?|harvests?)\b.{0,80}\b(employees?|users?|staff)?\b.{0,40}\b(login[- ]?codes?|one[- ]?time codes?|otp|mfa codes?|verification codes?)\b",
            r"\bfake\b.{0,40}\b(payroll|invoice)\b.{0,80}\b(email|message)\b.{0,100}\b(asks?|steal|capture|collect|enter|password|credential|one[- ]?time|otp|login code)\b",
            r"(釣魚|假登入|偽造登入|冒充|冒名|仿冒).{0,80}(密碼|憑證|驗證碼|一次性|權杖|帳號)",
        ),
    ),
    (
        "C2",
        (
            r"\b(bypass|evade|circumvent)\b.{0,80}\b(password|login|auth|authentication|mfa|permission|monitoring)\b",
            r"\b(disable|erase|delete|turn(?:ing)? off)\b.{0,80}\b(audit log|logs|logging|telemetry|monitoring|edr|antivirus|defender)\b",
            r"\b(collect|capture|harvest|obtain|copy(?:ing)?|steal(?:ing)?|extract(?:ing)?|exfiltrat(?:e|ing))\b.{0,100}\b(browser\s+)?session\s+(cookies?|tokens?)\b",
            r"\b(upload|send|post|transmit|exfiltrat(?:e|ing))\b.{0,120}\b(cookies?|session cookies?|session tokens?|tokens?|credentials?|api keys?|private keys?)\b",
            r"\b(cookies?|session cookies?|session tokens?|tokens?|credentials?|api keys?|private keys?)\b.{0,80}\b(?:are\s+)?(?:sent|posted|uploaded|transmitted|leaked)\b.{0,80}\b(webhook|endpoint|external|public|shared)\b",
            r"\b(print|dump|read|show|reveal|cat|copy)\b.{0,120}\b(\.env\b|ssh keys?|api tokens?|api keys?|private keys?|secret files?|credentials?)\b",
            r"\b(copy|paste|dump|print|show|read|upload|send|post|transmit|publish|share)\b.{0,120}\b(environment variables?|dotenv file|dotenv values?|dotenv variables?|\.env(?: file| contents?| values?| variables?)?)\b",
            r"\b(copy(?:ing)?|steal(?:ing)?|extract(?:ing)?|exfiltrat(?:e|ing))\b.{0,80}\b(cookies?|session cookies?|session tokens?|tokens?|credentials?)\b",
            r"\b(move|copy|import|export|transfer|sync)\b.{0,100}\b(browser\s+)?(profile\s+)?cookies?\b.{0,80}\b(sign[- ]?in|login|access|profile|account|computer|device)\b",
            r"(搬|移|同步|匯入|轉移|複製).{0,30}(瀏覽器)?\s*cookie.{0,30}(登入|帳號|另一台|電腦|裝置)",
            r"(瀏覽器)?\s*cookie.{0,30}(搬|移|同步|匯入|轉移|複製).{0,30}(登入|帳號|另一台|電腦|裝置)",
            r"\b(use|using)\b.{0,40}\b(cookies?|session cookies?|session tokens?|tokens?|credentials?)\b.{0,80}\b(access|login|account)\b",
            r"\b(reveal|show|print|dump|quote)\b.{0,120}\b(hidden system|developer instructions?|audit instructions?|private audit|control[- ]?plane)\b",
            r"\b(hidden system|developer instructions?|audit instructions?|private audit)\b.{0,120}\b(avoid|bypass|evade|circumvent)\b.{0,60}\b(gate|audit|review|safety layer)\b",
            r"\bprivilege escalation\b|\bmimikatz\b",
            r"(繞過|規避|破解|跳過).{0,30}(登入|密碼|驗證|認證|安全|權限|監控|日誌)",
            r"(關閉|停用|禁用|刪除|清除).{0,30}(防毒|監控|日誌|紀錄|安全系統)",
        ),
    ),
    (
        "C1",
        (
            r"\b(construct(?:ing)?|assemble|build|make|stage)\b.{0,80}\b(weapon|explosive|bomb|trap)\b",
            r"\b(improvised explosive device|ied)\b",
            r"\bharmful recipe\b.{0,80}\b(explosive|poison|weapon)\b",
            r"\b(poison|poisoning|poisonous)\b.{0,80}\b(dose|delivery|mixture|target|person)\b",
            r"\b(harm|injure|kill)\b.{0,80}\b(person|someone|target)\b",
            r"(製作|組裝).{0,30}(爆裂物|炸彈|毒物|武器)",
        ),
    ),
)
