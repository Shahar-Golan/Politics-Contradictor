# Stance Extraction Contract – v1

**Component:** `statement-processor`  
**Status:** Stable (v1)  
**Schema file:** `schemas/stance_extraction.schema.json`  
**Prompt template:** `prompts/stance_extraction_prompt.md`  
**Vocabularies (Python):** `src/contracts/vocab.py`  
**Vocabularies (JSON):** `src/contracts/vocab.json`  

---

## Purpose

This document defines the **stance extraction contract** – the machine-readable
interface that the stance extractor, schema validator, database writer, and test
suite all depend on.

The contract describes:
- what a **stance event** is,
- what fields every extraction result must contain,
- which field values are constrained to controlled vocabularies,
- what valid and invalid extractor output looks like.

---

## What is a stance event?

> Politician **P** expressed or enacted proposition **X** on topic **T**,
> supported by evidence **E**, in source document **D**.

One stance event is exactly one **atomic** instance of that pattern. Every field
in the schema corresponds to one component of that sentence.

### Atomicity

One extracted object = one atomic stance event.

| Rule | Example |
|---|---|
| Split distinct propositions | Biden supports minimum wage → Event 1; Biden opposes border wall → Event 2 |
| Do NOT merge claims | ~~"Biden supports wage increase and opposes the wall"~~ (bad) |
| Repeated identical mention | May be deduplicated (noted in `notes`) |
| Meaningfully distinct repetitions | Keep both with separate `event_date` or `evidence_role` |

---

## Top-level output shape

```json
{
  "doc_id": "string",
  "stance_events": [ ... ]
}
```

Both fields are **required**. Zero events is a valid and expected output:

```json
{
  "doc_id": "article-123",
  "stance_events": []
}
```

---

## StanceEvent fields

### Required fields

| Field | Type | Description |
|---|---|---|
| `politician` | string | Full name of the politician taking the stance. |
| `topic` | enum | High-level policy area. See [Controlled Vocabularies](#controlled-vocabularies). |
| `normalized_proposition` | string | A single declarative sentence summarising the stance in plain language. |
| `stance_direction` | enum | Direction of the stance. See [Controlled Vocabularies](#controlled-vocabularies). |
| `stance_mode` | enum | Form through which the stance is expressed. See [Controlled Vocabularies](#controlled-vocabularies). |
| `evidence_role` | enum | How the supporting evidence relates to the event. See [Controlled Vocabularies](#controlled-vocabularies). |
| `confidence` | float (0.0–1.0) | Extractor confidence in this event. 0.0 = no confidence, 1.0 = certain. |

### Optional fields

| Field | Type | Description |
|---|---|---|
| `subtopic` | string \| null | Finer-grained sub-category within `topic` (max 80 chars). |
| `speaker` | string \| null | Who delivered the statement (may differ from politician). |
| `target_entity` | string \| null | The entity the stance is directed at (person, country, bill, etc.). |
| `event_date` | string \| null | ISO-8601 date: `YYYY`, `YYYY-MM`, or `YYYY-MM-DD`. |
| `event_date_precision` | enum \| null | How precise `event_date` is. Required when `event_date` is set. |
| `quote_text` | string \| null | Verbatim text from the article supporting this event. |
| `quote_start_char` | integer \| null | 0-based start offset of `quote_text` in the article body. |
| `quote_end_char` | integer \| null | Exclusive end offset of `quote_text` in the article body. |
| `paraphrase` | string \| null | Brief paraphrase of the supporting evidence (max 200 chars). |
| `notes` | string \| null | Extraction caveats or edge-case notes (max 300 chars). |

**No additional properties are permitted** at either the top level or within a
stance event (`additionalProperties: false` in the schema).

---

## Controlled vocabularies

### `topic`

The supported policy areas for v1 extraction.

| Value | Meaning |
|---|---|
| `immigration` | Immigration, border policy, asylum, deportation |
| `trade` | Trade agreements, tariffs, import/export policy |
| `foreign_policy` | International relations, alliances, wars, sanctions |
| `abortion` | Reproductive rights, abortion access, related legislation |
| `healthcare` | Healthcare systems, insurance, drug pricing, public health |
| `economy` | General economic policy, jobs, wages, growth |
| `taxation` | Tax rates, tax cuts, tax enforcement |
| `crime` | Criminal justice, policing, sentencing |
| `climate` | Climate change, emissions, environmental regulation |
| `energy` | Energy production, fossil fuels, renewables |
| `elections` | Electoral rules, voting rights, election integrity |
| `democracy` | Democratic norms, institutions, rule of law |
| `other` | Any issue area not covered above |

### `stance_direction`

| Value | Meaning |
|---|---|
| `support` | Politician endorses or promotes the proposition |
| `oppose` | Politician rejects or argues against the proposition |
| `mixed` | Politician expresses both support and opposition (use sparingly; prefer two events) |
| `unclear` | Evidence is too ambiguous to assign a clear direction |

### `stance_mode`

| Value | Meaning |
|---|---|
| `statement` | A verbal declaration or public comment |
| `action` | A concrete act (signing a bill, issuing an order, casting a vote) |
| `promise` | A forward-looking commitment or pledge |
| `accusation` | One actor accuses another (populate `target_entity`) |
| `value_judgment` | An expression of values or moral framing without a specific policy claim |

### `evidence_role`

| Value | Meaning |
|---|---|
| `direct_quote` | Politician's exact words appear in quotation marks in the article |
| `reported_speech` | Article paraphrases what the politician said (e.g. "he said that…") |
| `inferred_from_action` | Stance inferred from a concrete act rather than words |
| `headline_claim` | Evidence comes only from the article headline |
| `summary_statement` | General characterisation by the article author without direct attribution |

### `event_date_precision`

| Value | Meaning |
|---|---|
| `day` | Date is known to the specific calendar day (`YYYY-MM-DD`) |
| `month` | Only the month is known (`YYYY-MM`) |
| `year` | Only the year is known (`YYYY`) |
| `approximate` | Date is estimated; add a note explaining the basis |

---

## Evidence handling guidance

| Evidence type | `evidence_role` | `stance_mode` | Notes |
|---|---|---|---|
| Exact words in quotes | `direct_quote` | any | Populate `quote_text` and offsets |
| Article says politician "stated" without full quotes | `reported_speech` | any | Populate `paraphrase` |
| Politician signed/blocked/ordered something | `inferred_from_action` | `action` | No quote expected |
| Headline only, body does not elaborate | `headline_claim` | any | Lower confidence, add note |
| Article author characterises stance without attribution | `summary_statement` | any | Confidence ≤ 0.5 recommended |
| Ambiguous evidence | `summary_statement` or `inferred_from_action` | any | Lower confidence, explain in `notes` |

---

## Atomicity examples

### Good extraction – two separate events

Article: *"Trump said he would close the border and impose 60% tariffs on China."*

```json
[
  {
    "politician": "Donald Trump",
    "topic": "immigration",
    "normalized_proposition": "Donald Trump supports closing the US southern border.",
    "stance_direction": "support",
    "stance_mode": "promise",
    "evidence_role": "reported_speech",
    "confidence": 0.9
  },
  {
    "politician": "Donald Trump",
    "topic": "trade",
    "normalized_proposition": "Donald Trump supports imposing 60% tariffs on Chinese imports.",
    "stance_direction": "support",
    "stance_mode": "promise",
    "evidence_role": "reported_speech",
    "confidence": 0.88
  }
]
```

### Bad extraction – merged propositions (do not do this)

```json
[
  {
    "politician": "Donald Trump",
    "topic": "immigration",
    "normalized_proposition": "Trump said he would close the border and impose 60% tariffs on China.",
    "stance_direction": "support",
    "stance_mode": "promise",
    "evidence_role": "reported_speech",
    "confidence": 0.9
  }
]
```

### Ambiguous edge case

Article: *"Biden is known for his moderate approach to healthcare reform."*  
No specific proposition is attributable. Use:

```json
{
  "politician": "Joe Biden",
  "topic": "healthcare",
  "normalized_proposition": "Joe Biden takes a moderate approach to healthcare reform.",
  "stance_direction": "unclear",
  "stance_mode": "value_judgment",
  "evidence_role": "summary_statement",
  "confidence": 0.35,
  "notes": "No specific policy claim; characterisation by article author only."
}
```

---

## Assumptions

1. Each input article is identified by a unique `doc_id` matching the
   `news_articles.doc_id` column in the local SQLite database.
2. The extractor reads one article at a time and returns one top-level JSON
   object per article.
3. The extractor output is produced by an LLM following
   `prompts/stance_extraction_prompt.md`.
4. All extractor output is validated against
   `schemas/stance_extraction.schema.json` before being persisted.
5. The schema's `additionalProperties: false` constraint means unknown fields
   will always be rejected by validators.

---

## How downstream code uses this contract

### Extractor implementation

1. Load the prompt template from `prompts/stance_extraction_prompt.md`.
2. Substitute `{{doc_id}}` and `{{article_text}}` placeholders.
3. Call the LLM.
4. Parse the LLM response as JSON.
5. Validate the parsed object against `schemas/stance_extraction.schema.json`.
6. If validation passes, pass the object to the database writer.

### Validator implementation

```python
import json
import jsonschema
from pathlib import Path

schema = json.loads(Path("schemas/stance_extraction.schema.json").read_text())

def validate_extraction(result: dict) -> None:
    jsonschema.validate(result, schema)
```

### Database writer

Map each item in `stance_events` to a row in `stance_records`, using the field
names directly (they align with the `stance_records` table columns defined in
`src/db/schema.sql`).

### Vocabulary checks

```python
from contracts.vocab import TOPIC_VALUES, STANCE_DIRECTION_VALUES

assert event["topic"] in TOPIC_VALUES
assert event["stance_direction"] in STANCE_DIRECTION_VALUES
```

---

## Example fixtures

| File | Description |
|---|---|
| `tests/fixtures/valid/zero_events.json` | Article with no extractable stances |
| `tests/fixtures/valid/single_direct_quote.json` | One clear direct-quote stance event |
| `tests/fixtures/valid/multiple_events.json` | Two events from one article |
| `tests/fixtures/valid/policy_action.json` | Policy action inferred from an executive order |
| `tests/fixtures/valid/reported_speech.json` | Reported speech with weaker evidence role |
| `tests/fixtures/invalid/malformed_json.txt` | Not valid JSON |
| `tests/fixtures/invalid/unsupported_vocab.json` | Invalid enum values (`"housing"`, `"yes"`, `"speech"`, `"quote"`) |
| `tests/fixtures/invalid/merged_propositions.json` | Single event containing multiple distinct claims |
| `tests/fixtures/invalid/missing_required_fields.json` | Event missing required fields |
| `tests/fixtures/invalid/text_outside_json.txt` | Narrative text wrapping the JSON object |

---

## Schema version history

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2026-03-14 | Initial contract. Five controlled vocabularies, 7 required fields, 10 optional fields. |

---

## Out of scope (v1)

- Live LLM calls or API integration
- Full extraction pipeline orchestration
- Database insertion logic
- Contradiction detection
- Dossier generation
- Large-scale evaluation harnesses
