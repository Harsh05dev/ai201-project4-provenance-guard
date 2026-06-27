def generate_label(attribution: str, confidence: float, verified: bool = False) -> str:
    pct = round(confidence * 100)

    if attribution == "likely_ai":
        body = (
            f"This content is likely AI-generated. Our analysis found strong patterns "
            f"consistent with automated writing (confidence: {pct}%). If you believe this "
            f"is incorrect, the creator can submit an appeal."
        )
    elif attribution == "likely_human":
        human_pct = round((1 - confidence) * 100)
        body = (
            f"This content appears to be human-written. Our analysis found patterns "
            f"consistent with authentic personal writing (confidence: {human_pct}%). "
            f"No action is needed unless you have reason to doubt this."
        )
    else:
        body = (
            f"We could not confidently determine whether this content is human-written or "
            f"AI-generated (confidence: {pct}%). The writing shows mixed signals. "
            f"Creators may appeal if they believe they were misclassified."
        )

    if verified:
        return f"[Verified Creator] This creator has completed identity attestation. {body}"
    return body
