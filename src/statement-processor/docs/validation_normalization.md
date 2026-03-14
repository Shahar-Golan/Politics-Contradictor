# Validation and Normalization Layer – v1

**Component:** `statement-processor`  
**Status:** Stable (v1)  
**Location:** `src/validation/`  
**Tests:** `tests/test_validation.py`, `tests/test_normalization.py`

---

## Purpose

This document describes the **deterministic validation and normalization layer**
that converts raw, untrusted LLM extractor output into clean, standardized
candidate stance events ready for safe downstream persistence.

The layer sits between the **extractor** (which produces `CandidateStanceEvent`
objects from LLM calls) and the **persistence layer** (which writes validated
events to Supabase):

```
Extractor → [raw JSON] → Validator → [validated] → Normalizer → [NormalizedStanceEvent] → (future) Persistence
```

---

## Design principles

| Principle | What it means |
|---|---|
| **Deterministic** | No LLM calls; same input always produces the same output. |
| **Conservative** | Ambiguous or unconfident cases emit warnings rather than silently accepting or aggressively rewriting. |
| **Separation of concerns** | Validation (accept/reject) is separate from normalization (transform accepted rows). |
| **Provenance preservation** | Raw values are stored alongside normalized values so any transformation can be audited. |
| **Easy to extend** | Normalization rules live in modular mappings, not monolithic functions. |

---

## Module structure

```
src/validation/
├── __init__.py               # Public API re-exports
├── models.py                 # Typed result models
├── errors.py                 # Error/warning codes and typed objects
├── validator.py              # Structural + semantic validator
├── normalizer.py             # Normalization orchestrator
├── date_parser.py            # Date parsing + standardization
├── politician_normalization.py  # Politician alias → canonical name
├── topic_normalization.py    # Surface form → controlled vocab topic
└── proposition_normalization.py  # Lexical proposition normalization
```

---

## Validation

### Entry point

```python
from validation.validator import validate_document

result = validate_document(raw_json_dict)
```

`validate_document` returns a `DocumentValidationResult` with:

- `status`: `VALID`, `VALID_WITH_WARNINGS`, or `REJECTED`
- `event_results`: per-event `EventValidationResult` objects
- `document_errors`: top-level structural errors
- `accepted_events` / `rejected_events` properties

### What is validated

**Document level**
- `doc_id` is present, a non-empty string
- `stance_events` is present and is a list

**Per event (required fields)**
- `politician`, `topic`, `normalized_proposition`, `stance_direction`,
  `stance_mode`, `evidence_role`, `confidence` — all must be present

**Vocabulary enforcement**
- `topic` ∈ `TOPIC_VALUES`
- `stance_direction` ∈ `STANCE_DIRECTION_VALUES`
- `stance_mode` ∈ `STANCE_MODE_VALUES`
- `evidence_role` ∈ `EVIDENCE_ROLE_VALUES`
- `event_date_precision` ∈ `EVENT_DATE_PRECISION_VALUES` (if present)

**Confidence**
- Must be a number (int or float)
- Must be in `[0.0, 1.0]`

**Date fields** (optional)
- If `event_date` is present, it must parse as `YYYY-MM-DD`, `YYYY-MM`, or `YYYY`
- If both `event_date` and `event_date_precision` are present, they must be consistent
- Impossible dates (e.g. `2024-02-31`) are rejected

**Evidence**
- `evidence_role == "direct_quote"` → `quote_text` must be present and non-empty
- Quote span offsets must be non-negative integers with `start < end`
- Span offsets without `quote_text` are rejected
- Missing `paraphrase` for `reported_speech` / `inferred_from_action` emits a warning

**Atomicity**
- If `normalized_proposition` contains ≥ 3 commas, the event is rejected as a
  likely merged multi-claim proposition

### Validation status

| Status | Meaning |
|---|---|
| `VALID` | All checks pass; no warnings. |
| `VALID_WITH_WARNINGS` | Accepted, but one or more soft issues were noted. |
| `REJECTED` | One or more hard errors; event must not be persisted. |

---

## Normalization

### Entry point

```python
from validation.normalizer import normalize_document

result = validate_document(raw_json)
normalized_events = normalize_document(result)
```

`normalize_document` skips rejected events and returns a
`list[NormalizedStanceEvent]` for all accepted events.

### Politician name normalization

Aliases are resolved to canonical names using the `_ALIAS_MAP` in
`politician_normalization.py`.

| Input | Canonical output |
|---|---|
| `"Trump"` | `"Donald Trump"` |
| `"President Trump"` | `"Donald Trump"` |
| `"former President Donald Trump"` | `"Donald Trump"` |
| `"Biden"` | `"Joe Biden"` |
| `"President Biden"` | `"Joe Biden"` |
| `"VP Harris"` | `"Kamala Harris"` |
| `"AOC"` | `"Alexandria Ocasio-Cortez"` |

Unknown politicians are **kept as-is** with a `WARN_UNKNOWN_POLITICIAN` warning.

**To add a new politician**, add a block to `_ALIAS_MAP` in
`politician_normalization.py`:
```python
"New Politician": frozenset({
    "new politician",
    "politician",
    "np",
}),
```

### Topic normalization

Topics not in the controlled vocabulary are mapped to the closest canonical
value using `_SURFACE_MAP` in `topic_normalization.py`.

| Input | Canonical output |
|---|---|
| `"tariffs"` | `"trade"` |
| `"border"` | `"immigration"` |
| `"climate change"` | `"climate"` |
| `"housing"` | `"other"` |
| Unknown topics | `"other"` |

Topics already in the controlled vocabulary pass through unchanged.

Unknown or out-of-scope topics are mapped to `"other"` with a
`WARN_TOPIC_MAPPED_TO_OTHER` warning.

### Proposition normalization

Deterministic lexical normalization is applied via phrase mappings in
`proposition_normalization.py`.

**Documented example (from the issue):**

| Input | Normalized output |
|---|---|
| `"raise tariffs on China"` | `"Raise tariffs on china"` |
| `"higher tariffs on Chinese imports"` | `"Raise tariffs on china"` |
| `"imposing 60 percent tariffs on goods imported from China"` | includes `"raise tariffs on china"` |

Additionally:
- Whitespace is normalized (collapsed, trimmed)
- Sentence case is applied
- Original proposition is preserved in `raw_proposition`

Propositions that cannot be confidently mapped are returned in their
whitespace-normalized, sentence-cased form without forced rewriting.

### Date normalization

Dates are parsed and standardized:

| Input format | Canonical output | Precision |
|---|---|---|
| `"2024-01-15"` | `"2024-01-15"` | `"day"` |
| `"2024-01"` | `"2024-01"` | `"month"` |
| `"2024"` | `"2024"` | `"year"` |

If `event_date_precision` is absent but `event_date` is parseable, precision
is inferred and a `WARN_DATE_PRECISION_INFERRED` warning is emitted.

### Confidence normalization

- Valid values `[0.0, 1.0]` are preserved exactly.
- Values outside the range are **clamped** with a `WARN_CONFIDENCE_CLAMPED` warning.
  (This should only occur for accepted events with edge-case float values; hard
  out-of-range values are already rejected by the validator.)

---

## Output model: `NormalizedStanceEvent`

The final output of the pipeline is a `NormalizedStanceEvent` dataclass that
contains:

**Normalized fields** (canonical, ready for persistence):
`politician`, `topic`, `normalized_proposition`, `stance_direction`,
`stance_mode`, `evidence_role`, `confidence`, `event_date`,
`event_date_precision`, plus all optional string/span fields.

**Raw / provenance fields** (populated only when normalization changed the value):
`raw_politician`, `raw_topic`, `raw_proposition`, `raw_event_date`.

**Status fields:**
`validation_status`, `validation_warnings`.

---

## Error and warning codes

All codes are defined as enums in `validation/errors.py`.

### `ErrorCode` (causes rejection)

| Code | Field | Meaning |
|---|---|---|
| `SHAPE_MISSING_DOC_ID` | `doc_id` | Top-level `doc_id` is absent |
| `SHAPE_EMPTY_DOC_ID` | `doc_id` | `doc_id` is an empty string |
| `SHAPE_MISSING_STANCE_EVENTS` | `stance_events` | `stance_events` is absent |
| `SHAPE_STANCE_EVENTS_NOT_LIST` | `stance_events` | `stance_events` is not an array |
| `SHAPE_EVENT_NOT_OBJECT` | — | An element in `stance_events` is not a dict |
| `FIELD_MISSING_REQUIRED` | varies | A required event field is missing |
| `FIELD_WRONG_TYPE` | varies | A field has the wrong type |
| `FIELD_INVALID_TOPIC` | `topic` | Topic not in controlled vocab |
| `FIELD_INVALID_STANCE_DIRECTION` | `stance_direction` | Invalid direction |
| `FIELD_INVALID_STANCE_MODE` | `stance_mode` | Invalid mode |
| `FIELD_INVALID_EVIDENCE_ROLE` | `evidence_role` | Invalid evidence role |
| `FIELD_INVALID_DATE_PRECISION` | `event_date_precision` | Invalid precision |
| `FIELD_CONFIDENCE_OUT_OF_RANGE` | `confidence` | Outside `[0.0, 1.0]` |
| `FIELD_CONFIDENCE_NOT_NUMBER` | `confidence` | Not a number |
| `FIELD_UNPARSEABLE_DATE` | `event_date` | Cannot be parsed |
| `FIELD_DATE_PRECISION_MISMATCH` | `event_date_precision` | Inconsistent with date |
| `EVIDENCE_MISSING_QUOTE` | `quote_text` | `direct_quote` requires `quote_text` |
| `EVIDENCE_EMPTY_QUOTE` | `quote_text` | `quote_text` is empty |
| `EVIDENCE_IMPLAUSIBLE_SPAN` | `quote_start_char` | Invalid span indices |
| `EVIDENCE_SPAN_WITHOUT_TEXT` | `quote_start_char` | Span present but no text |
| `ATOMICITY_MERGED_PROPOSITION` | `normalized_proposition` | Too many commas; likely merged |

### `WarningCode` (accepted with warning)

| Code | Field | Meaning |
|---|---|---|
| `WARN_POLITICIAN_NORMALIZED` | `politician` | Alias resolved to canonical |
| `WARN_UNKNOWN_POLITICIAN` | `politician` | Politician not in alias map |
| `WARN_TOPIC_NORMALIZED` | `topic` | Surface form mapped to canonical |
| `WARN_TOPIC_MAPPED_TO_OTHER` | `topic` | Unknown topic mapped to "other" |
| `WARN_PROPOSITION_NORMALIZED` | `normalized_proposition` | Phrase mapped to canonical |
| `WARN_DATE_NORMALIZED` | `event_date` | Date string transformed |
| `WARN_DATE_PRECISION_INFERRED` | `event_date_precision` | Precision inferred from date |
| `WARN_CONFIDENCE_CLAMPED` | `confidence` | Confidence clamped to range |
| `WARN_MISSING_EVIDENCE_PARAPHRASE` | `paraphrase` | Paraphrase absent for role |
| `WARN_ATOMICITY_POSSIBLE_MERGE` | `normalized_proposition` | Long proposition warning |

---

## Usage example

```python
import json
from validation.validator import validate_document
from validation.normalizer import normalize_document

raw = json.loads(open("extractor_output.json").read())

# Step 1: Validate
result = validate_document(raw)
print(f"Accepted: {result.accepted_count}, Rejected: {result.rejected_count}")

for rejected in result.rejected_events:
    for err in rejected.errors:
        print(f"  [{err.code}] {err.field}: {err.message}")

# Step 2: Normalize accepted events
normalized = normalize_document(result)
for event in normalized:
    print(f"  {event.politician} | {event.topic} | {event.normalized_proposition}")
    for warn in event.validation_warnings:
        print(f"    WARN [{warn.code}]: {warn.message}")
```

---

## Testing

Tests are in `tests/test_validation.py` and `tests/test_normalization.py`.

Run with:
```bash
cd src/statement-processor
python -m pytest tests/test_validation.py tests/test_normalization.py -v
```

Test fixtures used:

| Fixture | Type | Purpose |
|---|---|---|
| `valid/single_direct_quote.json` | valid | Full direct-quote event |
| `valid/multiple_events.json` | valid | Multi-event document |
| `valid/zero_events.json` | valid | Zero-event document |
| `valid/policy_action.json` | valid | Action-based event |
| `valid/reported_speech.json` | valid | Reported speech event |
| `valid/tariff_proposition.json` | valid | Tariff proposition for normalization |
| `valid/politician_aliases.json` | valid | Events with politician aliases |
| `invalid/missing_required_fields.json` | invalid | Missing required event fields |
| `invalid/unsupported_vocab.json` | invalid | Invalid vocabulary values |
| `invalid/merged_propositions.json` | invalid | Atomicity violation |
| `invalid/bad_confidence_type.json` | invalid | Non-numeric confidence |
| `invalid/bad_date_format.json` | invalid | Unparseable date |
| `normalized/tariff_expected.json` | reference | Expected normalized output |

---

## Out of scope

The following are **not** part of this layer:

- LLM extraction calls
- Contradiction / relation detection
- Dossier generation
- Final Supabase persistence (that is the next phase)
- Broad semantic reasoning beyond deterministic normalization
