import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

MODEL = "llama-3.3-70b-versatile"

PROMPT = """You are an expert at distinguishing human-written text from AI-generated text.

Analyze the following text and estimate the probability it was AI-generated.

Respond with ONLY valid JSON in this exact format:
{{"ai_likelihood": 0.75, "reasoning": "brief explanation"}}

ai_likelihood must be a float between 0.0 (definitely human) and 1.0 (definitely AI).

Text to analyze:
---
{text}
---"""


def _parse_score(raw: str) -> float:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("No JSON object in LLM response")
    data = json.loads(match.group())
    score = float(data["ai_likelihood"])
    return max(0.0, min(1.0, score))


def _heuristic_fallback(text: str) -> float:
    """Used when GROQ_API_KEY is unavailable (local dev without key)."""
    lower = text.lower()
    ai_markers = [
        "furthermore",
        "additionally",
        "it is important to note",
        "in conclusion",
        "paradigm",
        "stakeholders",
        "utilize",
        "leverage",
    ]
    hits = sum(1 for marker in ai_markers if marker in lower)
    words = max(len(text.split()), 1)
    density = hits / (words / 50)
    return max(0.0, min(1.0, 0.35 + density * 0.15))


def analyze_llm(text: str) -> float:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or api_key == "your_key_here":
        return _heuristic_fallback(text)

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": PROMPT.format(text=text[:4000])}],
        temperature=0.1,
        max_tokens=200,
    )
    raw = response.choices[0].message.content or ""
    try:
        return _parse_score(raw)
    except (ValueError, KeyError, json.JSONDecodeError):
        return _heuristic_fallback(text)
