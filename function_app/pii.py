import re


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d .()/-]{7,}\d)(?!\d)")


def redact_text(value: str) -> str:
    value = EMAIL_RE.sub("[redacted-email]", value)
    return PHONE_RE.sub("[redacted-phone]", value)
