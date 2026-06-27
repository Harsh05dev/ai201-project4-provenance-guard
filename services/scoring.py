AI_THRESHOLD = 0.72
HUMAN_THRESHOLD = 0.38

WEIGHTS = {
    "llm": 0.45,
    "stylometric": 0.35,
    "transition": 0.20,
}


def combine_signals(llm_score: float, stylometric_score: float, transition_score: float) -> dict:
    scores = [llm_score, stylometric_score, transition_score]
    spread = max(scores) - min(scores)

    raw = (
        WEIGHTS["llm"] * llm_score
        + WEIGHTS["stylometric"] * stylometric_score
        + WEIGHTS["transition"] * transition_score
    )

    high_agreement_ai = llm_score >= 0.8 and transition_score >= 0.7
    high_agreement_human = llm_score <= 0.4 and stylometric_score <= 0.4 and transition_score <= 0.4

    confidence = raw
    if high_agreement_ai:
        confidence = max(raw, 0.74)
    elif high_agreement_human:
        confidence = min(raw, 0.35)
    elif spread > 0.35:
        confidence = raw * 0.85 + 0.5 * 0.15

    confidence = round(max(0.0, min(1.0, confidence)), 4)

    if confidence >= AI_THRESHOLD:
        attribution = "likely_ai"
    elif confidence <= HUMAN_THRESHOLD:
        attribution = "likely_human"
    else:
        attribution = "uncertain"

    return {
        "confidence": confidence,
        "attribution": attribution,
        "signals": {
            "llm_score": round(llm_score, 4),
            "stylometric_score": round(stylometric_score, 4),
            "transition_score": round(transition_score, 4),
        },
        "signal_spread": round(spread, 4),
    }
