def classify(text: str) -> tuple[str, float]:
    """
    Classifies a complaint using simple keyword rules.

    This is an explainable baseline, not a production ML model.
    """

    if not isinstance(text, str):
        raise TypeError("text must be a string")

    normalised_text = text.lower()

    category_keywords = {
        "fees_and_charges": [
            "fee",
            "fees",
            "charge",
            "charged",
            "billing",
            "debited",
        ],
        "service_delay": [
            "delay",
            "delayed",
            "waiting",
            "wait",
            "slow",
            "no response",
            "response time",
        ],
        "misleading_conduct": [
            "mislead",
            "misleading",
            "wrong advice",
            "incorrect advice",
            "not told",
            "promised",
        ],
    }

    for category, keywords in category_keywords.items():
        if any(keyword in normalised_text for keyword in keywords):
            return category, 0.80

    return "uncategorised", 0.30