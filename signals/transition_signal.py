import re

TRANSITION_PHRASES = [
    "furthermore",
    "additionally",
    "moreover",
    "in conclusion",
    "it is important to note",
    "it is worth noting",
    "on the other hand",
    "in today's world",
    "as a result",
    "consequently",
    "in summary",
    "to summarize",
    "ultimately",
    "in other words",
    "that being said",
    "having said that",
    "needless to say",
    "at the end of the day",
    "plays a crucial role",
    "paradigm shift",
    "delve into",
    "landscape of",
    "it's worth mentioning",
]


def analyze_transitions(text: str) -> float:
    """Return 0-1 score where higher = more AI-like transition phrase density."""
    lower = text.lower()
    words = re.findall(r"[a-zA-Z']+", lower)
    word_count = max(len(words), 1)

    hits = sum(1 for phrase in TRANSITION_PHRASES if phrase in lower)
    per_100 = (hits / word_count) * 100

    if per_100 >= 3.0:
        return 0.9
    if per_100 >= 1.5:
        return 0.75
    if per_100 >= 0.8:
        return 0.6
    if per_100 >= 0.3:
        return 0.45
    return 0.25
