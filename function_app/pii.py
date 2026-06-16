import re


def redact(text: str) -> str:
    """
    Masks common personally identifiable information in complaint text.

    This is a lightweight baseline for demonstration purposes.
    It does not replace a production-grade PII detection service.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    # Email addresses
    text = re.sub(
        r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        text,
    )

    # Australian mobile phone numbers:
    # 0412 345 678, 0412345678, +61 412 345 678
    text = re.sub(
        r"(?<!\d)(?:\+61\s?4|04)\d{2}\s?\d{3}\s?\d{3}(?!\d)",
        "[PHONE]",
        text,
    )

    # Long numeric identifiers such as account or reference numbers
    text = re.sub(
        r"\b\d{6,}\b",
        "[ID]",
        text,
    )

    return text