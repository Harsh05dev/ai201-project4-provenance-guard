import math
import re
import statistics


def _sentences(text: str) -> list[str]:
    parts = re.split(r"[.!?]+", text)
    return [s.strip() for s in parts if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z']+", text.lower())


def analyze_stylometric(text: str) -> float:
    """Return 0-1 score where higher = more AI-like structural uniformity."""
    sentences = _sentences(text)
    words = _words(text)
    if len(words) < 5:
        return 0.5

    # Sentence length variance — AI tends toward uniform lengths
    if len(sentences) >= 2:
        lengths = [len(_words(s)) for s in sentences]
        mean_len = statistics.mean(lengths)
        variance = statistics.variance(lengths) if len(lengths) > 1 else 0
        cv = math.sqrt(variance) / mean_len if mean_len > 0 else 0
        variance_score = max(0.0, min(1.0, 1.0 - cv * 2.5))
    else:
        variance_score = 0.5

    # Type-token ratio — moderate diversity can indicate AI polish
    unique = len(set(words))
    ttr = unique / len(words)
    if ttr < 0.45:
        ttr_score = 0.7
    elif ttr < 0.65:
        ttr_score = 0.55
    elif ttr > 0.85:
        ttr_score = 0.3
    else:
        ttr_score = 0.45

    # Punctuation density — AI often uses consistent comma patterns
    punct_count = len(re.findall(r"[,;:—–-]", text))
    punct_density = punct_count / len(words)
    if 0.08 <= punct_density <= 0.18:
        punct_score = 0.65
    elif punct_density < 0.05:
        punct_score = 0.35
    else:
        punct_score = 0.5

    return round(0.45 * variance_score + 0.35 * ttr_score + 0.20 * punct_score, 4)
