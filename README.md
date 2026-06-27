# Provenance Guard

Backend API for classifying creative content as human-written or AI-generated, with transparency labels, appeals, audit logging, and production safety features.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add GROQ_API_KEY
python app.py
```

Server runs at **http://127.0.0.1:5000/**

## Architecture Overview

A submission flows through these components:

1. **Rate limiter** — checks IP against 10/min and 100/day limits
2. **Content normalizer** — extracts analyzable text from `text`, `image_description`, or `metadata` payloads
3. **Signal 1 (Groq LLM)** — holistic semantic AI-likelihood score
4. **Signal 2 (Stylometrics)** — structural uniformity score (sentence variance, vocabulary, punctuation)
5. **Signal 3 (Transition phrases)** — density of common AI connector phrases
6. **Ensemble scorer** — weighted combination with disagreement dampening
7. **Label generator** — maps score to plain-language transparency label (+ verified badge if applicable)
8. **Audit log** — structured SQLite entry with all scores and metadata

Appeals update content status to `under_review` and append an appeal entry to the audit log alongside the original classification.

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/submit` | Submit content for classification |
| POST | `/appeal` | Contest a classification |
| POST | `/verify` | Earn verified human certificate |
| GET | `/log` | Audit log (JSON) |
| GET | `/dashboard` | Analytics dashboard (HTML) |
| GET | `/dashboard?format=json` | Analytics metrics (JSON) |

### Example: Submit

```bash
curl -s -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"text": "The sun dipped below the horizon...", "creator_id": "test-user-1"}' | python3 -m json.tool
```

### Example: Appeal

```bash
curl -s -X POST http://127.0.0.1:5000/appeal \
  -H "Content-Type: application/json" \
  -d '{"content_id": "YOUR-CONTENT-ID", "creator_reasoning": "I wrote this myself from personal experience."}' | python3 -m json.tool
```

## Detection Signals

### Signal 1: Groq LLM (semantic)
- **Measures:** Whether prose reads like typical LLM output — polished coherence, generic phrasing, balanced structure.
- **Why chosen:** Captures meaning-level patterns that heuristics miss.
- **Blind spot:** Formal human academic writing can appear AI-like.

### Signal 2: Stylometric heuristics (structural)
- **Measures:** Sentence length variance, type-token ratio, punctuation density.
- **Why chosen:** AI text tends toward uniform structure; human writing varies more.
- **Blind spot:** Deliberately polished marketing copy or poetry with repetition.

### Signal 3: Transition phrase density (lexical) — ensemble stretch
- **Measures:** Frequency of phrases like "Furthermore," "It is important to note," "In conclusion."
- **Why chosen:** LLMs overuse templated discourse markers.
- **Blind spot:** Formal academic essays with heavy transitions.

**Ensemble weighting:** `0.45 × LLM + 0.35 × stylometric + 0.20 × transition`. When LLM and transition strongly agree on AI (≥0.8 and ≥0.7), confidence is boosted. When signals disagree (spread >0.35), score is pulled toward 0.5 to reduce false positives.

## Confidence Scoring

| Range | Attribution | Label variant |
|-------|-------------|---------------|
| ≥ 0.72 | `likely_ai` | High-confidence AI |
| 0.38–0.72 | `uncertain` | Uncertain |
| ≤ 0.38 | `likely_human` | High-confidence human |

**Validation:** Tested four reference texts — clearly AI, clearly human, formal human, borderline AI. Scores span ~0.20–0.74 rather than clustering at 0.5.

### Example submissions with different scores

**High-confidence AI (confidence: 0.74)**
```
Text: "Artificial intelligence represents a transformative paradigm shift..."
Attribution: likely_ai
Signals: llm=0.90, stylometric=0.175, transition=0.90
```

**High-confidence human (confidence: 0.20)**
```
Text: "ok so i finally tried that new ramen place downtown and honestly? underwhelming..."
Attribution: likely_human
Signals: llm=0.15, stylometric=0.17, transition=0.25
```

## Transparency Labels

Exact text displayed to readers:

| Variant | Exact label text |
|---------|-----------------|
| **High-confidence AI** | "This content is likely AI-generated. Our analysis found strong patterns consistent with automated writing (confidence: {pct}%). If you believe this is incorrect, the creator can submit an appeal." |
| **High-confidence human** | "This content appears to be human-written. Our analysis found patterns consistent with authentic personal writing (confidence: {pct}%). No action is needed unless you have reason to doubt this." |
| **Uncertain** | "We could not confidently determine whether this content is human-written or AI-generated (confidence: {pct}%). The writing shows mixed signals. Creators may appeal if they believe they were misclassified." |
| **Verified creator overlay** | "[Verified Creator] This creator has completed identity attestation. " + standard label above |

## Rate Limiting

**Limits:** `10 per minute; 100 per day` per IP on `POST /submit`

**Reasoning:** A writer revising drafts might submit 3–5 times in a session; 10/min allows burst editing. 100/day prevents scripted flooding while allowing prolific creators (~3 posts/hour over a full day).

**Evidence (12 rapid requests):**
```
200 200 200 200 200 200 200 200 200 200 429 429
```

Test with:
```bash
for i in $(seq 1 12); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:5000/submit \
    -H "Content-Type: application/json" \
    -d '{"text": "Rate limit test", "creator_id": "ratelimit-test"}'
done
```

## Audit Log Sample

`GET /log` returns structured JSON. Example entries (abbreviated):

```json
{
  "entries": [
    {
      "content_id": "5e26355c-...",
      "creator_id": "demo-human",
      "timestamp": "2026-06-27T22:52:18+00:00",
      "attribution": "likely_human",
      "confidence": 0.2012,
      "llm_score": 0.15,
      "stylometric_score": 0.17,
      "transition_score": 0.25,
      "status": "classified"
    },
    {
      "content_id": "5e26355c-...",
      "creator_id": "demo-human",
      "timestamp": "2026-06-27T22:52:19+00:00",
      "event": "appeal_filed",
      "original_attribution": "likely_human",
      "original_confidence": 0.2012,
      "appeal_reasoning": "I wrote this myself from personal experience at the ramen shop.",
      "status": "under_review"
    }
  ]
}
```

## Stretch Features

### Ensemble Detection (+1)
Three signals with documented weights (see Detection Signals). Individual scores returned in every `/submit` response and logged.

### Provenance Certificate (+1)
Creators call `POST /verify` with a 20+ word first-person attestation phrase. Verified creators receive a `[Verified Creator]` badge prepended to all future transparency labels.

```bash
curl -X POST http://127.0.0.1:5000/verify \
  -H "Content-Type: application/json" \
  -d '{"creator_id": "your-name", "attestation_phrase": "I am writing this to confirm that I personally authored..."}'
```

### Analytics Dashboard (+1)
Visit **http://127.0.0.1:5000/dashboard** for:
- Detection pattern breakdown (AI vs human vs uncertain %)
- Appeal rate
- Average confidence score
- Verified creator count

### Multi-Modal Support (+1)
`POST /submit` accepts `content_type`:
- `text` (default) — standard text analysis
- `image_description` — alt-text / image description analyzed as text
- `metadata` — JSON object with `title`, `bio`, `tags`, `description` serialized and analyzed

```bash
curl -X POST http://127.0.0.1:5000/submit \
  -H "Content-Type: application/json" \
  -d '{"content_type": "metadata", "creator_id": "photo-user", "metadata": {"title": "Sunset", "bio": "I shot this last summer", "tags": ["nature"]}}'
```

## Known Limitations

**Formal academic prose** is likely to score as AI-generated because stylometric uniformity and transition-phrase signals both fire on polished, structured writing — even when a human author wrote it carefully. The wide uncertain band and appeals workflow exist specifically to handle this case.

## Spec Reflection

**How the spec helped:** Writing label variants and confidence thresholds in `planning.md` before coding meant the label function, scoring thresholds, and API response shape were already defined — implementation was mostly wiring, not re-deciding UX mid-build.

**Where implementation diverged:** The spec called for symmetric disagreement dampening, but testing showed clearly-AI text with low stylometric scores getting pulled below the 0.72 threshold. I added an "AI agreement bypass" when LLM and transition scores both strongly indicate AI, so obvious AI text still reaches the high-confidence label.

## AI Usage

1. **Flask app skeleton + Groq signal (M3):** Directed AI to generate the Flask route structure and LLM prompt from the detection signals section of `planning.md`. **Revised:** Changed audit log to SQLite instead of in-memory list; fixed the Groq prompt JSON braces that broke Python `.format()`.

2. **Ensemble scoring + stylometric signal (M4):** Asked AI to implement stylometric heuristics and weighted scoring from the spec. **Revised:** Added asymmetric agreement logic after test inputs showed formal AI text scoring below 0.72 due to stylometric blind spots; adjusted weights handling in the agreement bypass rather than using AI's symmetric dampening alone.

3. **Production layer + stretch features (M5–6):** Generated appeal endpoint, Flask-Limiter setup, and dashboard HTML from the appeals workflow and stretch sections. **Revised:** Added multi-modal text normalization manually; tightened verify attestation validation to require first-person language.

## Project Structure

```
app.py                  # Flask routes
planning.md             # Pre-implementation spec
signals/
  llm_signal.py         # Signal 1: Groq
  stylometric_signal.py # Signal 2: structure
  transition_signal.py  # Signal 3: phrase density
services/
  scoring.py            # Ensemble combination
  labels.py             # Transparency labels
  audit.py              # Audit log
  storage.py            # SQLite
  content.py            # Appeals + multi-modal
  analytics.py          # Dashboard metrics
```
