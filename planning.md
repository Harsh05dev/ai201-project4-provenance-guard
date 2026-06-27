# Provenance Guard — Planning Spec

Written before implementation. Updated before stretch features.

## Architecture

### Narrative

When a creator submits text (or image description / metadata), the request enters the Flask API at `POST /submit`. Rate limiting runs first. The pipeline runs three detection signals in parallel conceptually: (1) Groq LLM holistic classification, (2) stylometric heuristics on sentence structure and vocabulary, and (3) transition-phrase density scoring. A weighted ensemble combines these into a single AI-likelihood confidence score (0–1, higher = more likely AI). The score maps to one of three transparency labels. The decision, all signal scores, and metadata are written to a SQLite audit log. The JSON response returns `content_id`, attribution, confidence, label text, signal breakdown, and certificate status if applicable.

For appeals, the creator calls `POST /appeal` with `content_id` and `creator_reasoning`. The system validates ownership, sets status to `under_review`, appends appeal details to the audit log, and returns confirmation. A human reviewer would see the original classification, signal scores, and appeal reasoning in the log queue.

For provenance certificates, verified creators call `POST /verify` once with a short handwritten-style attestation phrase. After passing a consistency check, they earn a `verified_human` credential stored per `creator_id`. Future submissions show a distinct verified badge on the transparency label.

Multi-modal support: `POST /submit` accepts `content_type` of `text` (default), `image_description`, or `metadata`. Text signals run on the primary `text` field; for `metadata`, signals adapt to JSON-serialized structured fields (title, tags, bio).

### Diagram

```
SUBMISSION FLOW
===============

  Client                    Flask API                 Detection Pipeline              Storage
    |                          |                              |                          |
    |  POST /submit            |                              |                          |
    |  {text, creator_id}      |                              |                          |
    |------------------------->|  rate limit check            |                          |
    |                          |------------------------------|                          |
    |                          |  Signal 1: Groq LLM          |                          |
    |                          |  (semantic AI likelihood)    |                          |
    |                          |------------------------------|                          |
    |                          |  Signal 2: Stylometrics      |                          |
    |                          |  (structure / vocabulary)    |                          |
    |                          |  Signal 3: Transition density  |                          |
    |                          |  (connector phrase patterns)   |                          |
    |                          |------------------------------|                          |
    |                          |  Ensemble scoring            |                          |
    |                          |  (weighted combine)          |                          |
    |                          |------------------------------|                          |
    |                          |  Label generator             |                          |
    |                          |  (+ verified badge if cert)  |                          |
    |                          |------------------------------|                          |
    |                          |  audit log write             |------------------------->|
    |                          |                              |         SQLite           |
    |  JSON response           |                              |                          |
    |<-------------------------|                              |                          |

APPEAL FLOW
===========

  Client                    Flask API                 Storage
    |                          |                          |
    |  POST /appeal            |                          |
    |  {content_id, reason}    |                          |
    |------------------------->|  lookup content          |------------------------->|
    |                          |  status -> under_review  |------------------------->|
    |                          |  log appeal entry        |------------------------->|
    |  confirmation            |                          |
    |<-------------------------|                          |

VERIFICATION FLOW (stretch)
===========================

  Client                    Flask API                 Storage
    |                          |                          |
    |  POST /verify            |                          |
    |  {creator_id, phrase}    |                          |
    |------------------------->|  validate attestation    |------------------------->|
    |                          |  grant verified_human    |------------------------->|
    |  certificate granted     |                          |
    |<-------------------------|                          |
```

## Detection Signals

### Signal 1: Groq LLM Classification (semantic)

- **Measures:** Holistic semantic and stylistic coherence — whether prose reads like typical LLM output (balanced clauses, generic transitions, polished uniformity).
- **Output:** Float 0.0–1.0 where 1.0 = model is highly confident the text is AI-generated.
- **Why it differs:** LLMs produce semantically coherent, evenly structured text; humans often have idiosyncrasies, typos, and uneven rhythm.
- **Blind spot:** Formal human academic writing can look "AI-like" to an LLM. Non-native speakers writing carefully may score high.

### Signal 2: Stylometric Heuristics (structural)

- **Measures:** Sentence length variance, type-token ratio (vocabulary diversity), and punctuation density.
- **Output:** Float 0.0–1.0 (higher = more AI-like uniformity).
- **Why it differs:** AI text tends toward uniform sentence lengths and moderate vocabulary diversity; human casual writing varies more.
- **Blind spot:** Deliberately polished human copy (marketing, essays) may look uniform. Poetry with repetition scores artificially "AI."

### Signal 3: Transition Phrase Density (lexical pattern) — stretch ensemble

- **Measures:** Frequency of common LLM connector phrases ("Furthermore," "Additionally," "It is important to note," "In conclusion").
- **Output:** Float 0.0–1.0 based on normalized phrase count per 100 words.
- **Why it differs:** AI models overuse templated discourse markers; humans use them less densely unless writing formal essays.
- **Blind spot:** Academic human essays with heavy transitions score high.

### Combining Signals (ensemble)

Weighted average with false-positive bias (human misclassification is worse):

```
confidence = 0.45 * llm_score + 0.35 * stylometric_score + 0.20 * transition_score
```

When signals disagree by >0.35 spread, pull confidence toward 0.5 (uncertainty zone) by 15% to avoid overconfident wrong labels.

Attribution mapping:
- `confidence >= 0.72` → `likely_ai`
- `confidence <= 0.38` → `likely_human`
- else → `uncertain`

## Uncertainty Representation

- **0.5 means:** Genuinely ambiguous — signals disagree or text sits in the borderline band. The label says we cannot confidently determine origin.
- **Calibration:** Tested on four reference texts (clearly AI, clearly human, formal human, lightly edited AI). Scores should span roughly 0.15–0.85, not cluster at 0.5.
- **Thresholds:**
  - High-confidence AI: >= 0.72
  - Uncertain: 0.38–0.72
  - High-confidence human: <= 0.38
- **Asymmetry:** Disagreement dampening and wider uncertain band (0.38–0.72 vs symmetric 0.35–0.65) reduce false positives on human writers.

## Transparency Label Variants

Exact text shown to readers:

**High-confidence AI (confidence >= 0.72):**
> "This content is likely AI-generated. Our analysis found strong patterns consistent with automated writing (confidence: {pct}%). If you believe this is incorrect, the creator can submit an appeal."

**High-confidence human (confidence <= 0.38):**
> "This content appears to be human-written. Our analysis found patterns consistent with authentic personal writing (confidence: {pct}%). No action is needed unless you have reason to doubt this."

**Uncertain (0.38 < confidence < 0.72):**
> "We could not confidently determine whether this content is human-written or AI-generated (confidence: {pct}%). The writing shows mixed signals. Creators may appeal if they believe they were misclassified."

**Verified human certificate overlay (when creator is verified):**
> "[Verified Creator] This creator has completed identity attestation. " + (standard label above)

`{pct}` = rounded `(confidence * 100)` for AI-likelihood when result is `likely_ai`, or `(100 - confidence * 100)` for human-likelihood when `likely_human`, or shown as ambiguity percentage for uncertain.

## Appeals Workflow

- **Who:** Any creator who submitted content (matched by `creator_id` on original submission).
- **Input:** `content_id`, `creator_reasoning` (free text, min 10 chars).
- **Actions:**
  1. Validate content exists and is not already under review.
  2. Update content status to `under_review`.
  3. Append audit log entry with original decision, appeal reasoning, timestamp.
  4. Return `{status: "under_review", message: "Appeal received..."}`.
- **Reviewer view:** Log entry shows original attribution, confidence, all signal scores, creator_id, appeal_reasoning, timestamps.

## Anticipated Edge Cases

1. **Formal academic prose:** Stylometrics and transition signal may score high; LLM may agree → false positive risk. Mitigated by uncertain band and appeals.
2. **Poetry with repetition:** Low sentence-length variance triggers stylometric false AI signal; disagreement dampening should widen uncertainty.
3. **Non-native English writers:** Careful grammar and formal tone may resemble AI; appeals path is critical.
4. **Very short submissions (<50 words):** Insufficient text for reliable stylometrics; return lower confidence cap or note in response.

## Rate Limiting Plan

- `10 per minute; 100 per day` per IP on `POST /submit`.
- **Reasoning:** A writer might submit 3–5 drafts while editing; 10/min allows burst revision without abuse. 100/day caps scripted flooding while allowing prolific creators.

## Stretch Features Plan

### Ensemble Detection (+1)
Three signals with documented weights above. Individual scores returned in API and logged.

### Provenance Certificate (+1)
`POST /verify` with `creator_id` + `attestation_phrase` (min 20 words, must include first-person language). One-time verification per creator. Verified badge prepended to label.

### Analytics Dashboard (+1)
`GET /dashboard` HTML view: AI vs human vs uncertain ratio, appeal rate, average confidence score.

### Multi-Modal Support (+1)
`content_type`: `text` | `image_description` | `metadata`. Metadata analyzed via serialized JSON string; image descriptions run full text pipeline.

## AI Tool Plan

### M3 — Submission endpoint + Signal 1
- **Spec sections:** Detection signals (Signal 1), Architecture diagram, API contract.
- **Ask AI to generate:** Flask skeleton, `POST /submit`, Groq signal function, SQLite audit log, `GET /log`.
- **Verify:** curl submit returns content_id; log entry appears; signal 1 score populated.

### M4 — Signal 2 + confidence scoring
- **Spec sections:** Detection signals (all), Uncertainty representation, Architecture diagram.
- **Ask AI to generate:** Stylometric + transition signal functions, ensemble scoring, updated audit log fields.
- **Verify:** Four test inputs produce meaningfully different scores; log shows all signal scores.

### M5 — Production layer
- **Spec sections:** Transparency labels, Appeals workflow, Rate limiting plan, Architecture diagram.
- **Ask AI to generate:** Label function, `POST /appeal`, Flask-Limiter on submit.
- **Verify:** Three label variants reachable; appeal updates status; rate limit returns 429.

### M6 — Stretch + documentation
- **Spec sections:** Stretch features plan.
- **Ask AI to generate:** `POST /verify`, dashboard template, multi-modal handling in submit.
- **Verify:** Dashboard shows 3+ metrics; verified label distinct; metadata submission works.
