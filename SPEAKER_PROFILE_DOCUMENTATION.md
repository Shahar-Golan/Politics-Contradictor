# Speaker Profile Data Structure & Component Documentation

## Overview
This document comprehensively maps how speaker profiles are:
1. Fetched from the API (`api/index.py`)
2. Rendered in React components (`frontend/src/components/SpeakerProfile.jsx`)
3. Processed by Python backend (`src/agents/page_lookup.py`)
4. Enriched with news data (`src/rss-extractor/src/services/speaker_profile_enrichment.py`)

---

## 1. REACT COMPONENT: SpeakerProfile.jsx

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/frontend/src/components/SpeakerProfile.jsx`

### Component Overview
- **Purpose:** Display speaker profiles with multiple tabbed sections
- **Main State:** `selectedProfile` (the currently viewed profile object)
- **Sections Rendered:** 8 tabs (Bio, Notable Topics, Timeline, Controversies, Relationships, Public Perception, Media Profile, Dataset Insights)

### API Calls
- `chatAPI.getSpeakers()` → Returns array of speaker summaries for sidebar
- `chatAPI.getSpeakerProfile(speakerId)` → Returns full profile object

### Section-by-Section Field Access

#### Section 1: Bio (renderBio)
**Top-level key accessed:** `profile.bio`

**Fields read from bio:**
- `bio.full_name` — String, displayed as "Full Name"
- `bio.born` — String, displayed as "Born"
- `bio.party` — String, displayed as "Party"
- `bio.current_role` — String, displayed as "Current Role"
- `bio.net_worth_estimate` — String, displayed as "Net Worth"
- `bio.previous_roles` — **Array** of strings, iterated with `.map()`, each item is a simple string
- `bio.education` — **Array** of strings, iterated with `.map()`, each item is a simple string

**Conditional rendering:** Uses `?.` optional chaining and `||` fallback to "N/A"

---

#### Section 2: Notable Topics (renderTopics)
**Top-level key accessed:** `profile.notable_topics`

**Field structure:** Array of topic objects, each with:
- `topic.topic` — String, the topic name (displayed in header)
- `topic.category` — String, category badge
- `topic.stance` — String, the speaker's stance on the topic
- `topic.key_statements` — **Array** of strings (quotes), iterated with `.map()`
- `topic.evolution` — String (optional), displayed if exists
- `topic.controversies` — String (optional), displayed if exists

**Array iteration:**
```javascript
topics.map((topic, i) => (
  // Each item: { topic, category, stance, key_statements[], evolution?, controversies? }
))
```

---

#### Section 3: Timeline (renderTimeline)
**Top-level key accessed:** `profile.timeline_highlights`

**Field structure:** Array of event objects, each with:
- `event.year` — String, the year of the event
- `event.event` — String, the event title
- `event.significance` — String, why it matters

**Array iteration:**
```javascript
events.map((event, i) => (
  // Each item: { year, event, significance }
))
```

---

#### Section 4: Controversies (renderControversies)
**Top-level key accessed:** `profile.controversies`

**Field structure:** Array of controversy objects, each with:
- `controversy.title` — String, controversy name (displayed in header)
- `controversy.year` — String, year badge
- `controversy.description` — String, the controversy details
- `controversy.outcome` — String (optional), displayed if exists with "Outcome:" label
- `controversy.impact` — String (optional), displayed if exists with "Impact:" label

**Array iteration:**
```javascript
items.map((item, i) => (
  // Each item: { title, year, description, outcome?, impact? }
))
```

---

#### Section 5: Relationships (renderRelationships)
**Top-level key accessed:** `profile.relationships`

**Field structure:** Object with:
- `relationships.allies` — **Array** of strings (names), iterated with `.map()`
- `relationships.opponents` — **Array** of strings (names), iterated with `.map()`
- `relationships.co_mentioned_figures` — **Object** where keys are names, values are numbers (article counts)
  - Iterated with `Object.entries()`, rendering as `[name, count]` pairs
  - `count.toLocaleString()` is called (so value is numeric)
- `relationships.relationship_context` — String, displayed under "Context" heading

**Special handling:**
```javascript
// co_mentioned_figures iteration
Object.entries(rel.co_mentioned_figures).map(([name, count]) => (
  // name is string, count is number
  <span>{name}: {count.toLocaleString()} articles</span>
))
```

---

#### Section 6: Public Perception (renderPerception)
**Top-level key accessed:** `profile.public_perception`

**Field structure:** Object with:
- `public_perception.approval_trend` — String (optional)
- `public_perception.base_support` — String (optional)
- `public_perception.opposition` — String (optional)
- `public_perception.key_narratives` — **Array** of strings, iterated with `.map()`

**Conditional rendering:** Each field only rendered if truthy (uses `&&` conditional)

---

#### Section 7: Media Profile (renderMedia)
**Top-level key accessed:** `profile.media_profile`

**Field structure:** Object with:
- `media_profile.coverage_volume` — String (optional)
- `media_profile.top_covering_states` — **Object** where keys are state names, values are counts (numbers)
  - Iterated with `Object.entries()` and rendered as bars with `width: ${(count / max) * 100}%`
- `media_profile.media_narrative` — String (optional)
- `media_profile.sentiment_trend` — String (optional)

**Special handling:**
```javascript
// Computes max value to normalize bar widths
const max = Math.max(...Object.values(mp.top_covering_states));
Object.entries(mp.top_covering_states).map(([state, count]) => (
  // state is string, count is number
  <div style={{ width: `${(count / max) * 100}%` }} />
))
```

---

#### Section 8: Dataset Insights (renderDataInsights)
**Top-level key accessed:** `profile.dataset_insights`

**Field structure:** Object with:
- `dataset_insights.total_articles` — Number, displayed with `.toLocaleString()`
- `dataset_insights.date_range` — String (e.g., "2020-01-01 to 2025-03-15")
- `dataset_insights.top_title_keywords` — **Object** where keys are words, values are counts (numbers)
  - Iterated with `Object.entries()` and rendered as keyword tags
- `dataset_insights.geographic_focus` — String (optional)

**Special handling:**
```javascript
Object.entries(di.top_title_keywords).map(([word, count]) => (
  // word is string, count is number
  <span>{word} ({count})</span>
))
```

---

### Header Display
The profile header displays:
- `selectedProfile.name` — String
- `selectedProfile.bio?.current_role` — String (with optional chaining)

---

### Sidebar Speaker List
When listing speakers, the component reads from the summary array:
- `speaker.speaker_id` — String, used as React key and for fetching
- `speaker.name` — String
- `speaker.party` — String
- `speaker.total_articles` — Number, displayed with `.toLocaleString()`

---

## 2. FLASK API ENDPOINTS

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/api/index.py`

### GET /api/speakers
**Returns:** Array of speaker summary objects

**Response structure:**
```json
[
  {
    "speaker_id": "donald_trump",
    "name": "Donald Trump",
    "party": "Republican",
    "current_role": "Former President",
    "born": "1946",
    "total_articles": 1250
  }
]
```

**Query:** Fetches from `speaker_profiles` table:
```sql
SELECT speaker_id, name, party, "current_role",
       profile->'bio'->>'born' as born,
       profile->'dataset_insights'->>'total_articles' as total_articles
FROM speaker_profiles ORDER BY name
```

---

### GET /api/speakers/<speaker_id>
**Returns:** Full profile object for a single speaker

**Response structure:** The raw `profile` JSONB column from the database, plus `updated_at` timestamp

**Query:** Fetches the full profile JSONB:
```sql
SELECT profile, updated_at FROM speaker_profiles WHERE speaker_id = %s
```

**Top-level keys in the profile object:**
- `name` — String, speaker's full name
- `bio` — Object (see below)
- `notable_topics` — Array of topic objects
- `timeline_highlights` — Array of event objects
- `controversies` — Array of controversy objects
- `relationships` — Object
- `public_perception` — Object
- `media_profile` — Object
- `dataset_insights` — Object
- `recent_news` — Object (added by enrichment pipeline)
- `updated_at` — String (ISO 8601 timestamp, added by API)

---

## 3. PROFILE JSON STRUCTURE (Full Schema)

Based on React component field access and enrichment code:

```json
{
  "name": "Donald Trump",
  "bio": {
    "full_name": "Donald John Trump",
    "born": "June 14, 1946",
    "party": "Republican",
    "current_role": "Former President",
    "net_worth_estimate": "$2.6 billion",
    "previous_roles": [
      "Real Estate Developer",
      "Television Personality"
    ],
    "education": [
      "Wharton School of Business (1968)"
    ]
  },
  "notable_topics": [
    {
      "topic": "Immigration",
      "category": "Policy",
      "stance": "Restrictive enforcement",
      "key_statements": [
        "We need to build a wall",
        "We have to secure our borders"
      ],
      "evolution": "Consistently hardline from 2015-present",
      "controversies": "Criticized for inflammatory rhetoric"
    }
  ],
  "timeline_highlights": [
    {
      "year": "2015",
      "event": "Announced presidential campaign",
      "significance": "Disrupted Republican primary"
    }
  ],
  "controversies": [
    {
      "title": "Access Hollywood tape",
      "year": "2005",
      "description": "Recording of Trump making lewd comments",
      "outcome": "Denied allegations, remained in race",
      "impact": "Sparked #MeToo discussions, but campaign survived"
    }
  ],
  "relationships": {
    "allies": [
      "Rupert Murdoch",
      "Steve Bannon"
    ],
    "opponents": [
      "Hillary Clinton",
      "Barack Obama"
    ],
    "co_mentioned_figures": {
      "Hillary Clinton": 4521,
      "Joe Biden": 3841,
      "Barack Obama": 2156
    },
    "relationship_context": "Has maintained rivalry with Clinton; complex relationship with establishment Republicans"
  },
  "public_perception": {
    "approval_trend": "Highly polarized; consistently 35-45% approval",
    "base_support": "Strong among blue-collar workers and rural voters",
    "opposition": "Opposes expand social programs, concerned about norms",
    "key_narratives": [
      "Anti-establishment outsider",
      "Business success vs. ethical concerns"
    ]
  },
  "media_profile": {
    "coverage_volume": "Highest coverage of any political figure in 2024",
    "top_covering_states": {
      "New York": 1245,
      "California": 892,
      "Texas": 756
    },
    "media_narrative": "Polarizing figure with strong opinions on trade and immigration",
    "sentiment_trend": "Becomes more negative during scandals"
  },
  "dataset_insights": {
    "total_articles": 4521,
    "date_range": "2015-01-01 to 2025-03-15",
    "top_title_keywords": {
      "Trump": 3892,
      "President": 2154,
      "Election": 1876
    },
    "geographic_focus": "Heavily covered in national outlets; especially in politics/news sections"
  },
  "recent_news": {
    "summary": "Latest developments about the figure",
    "last_updated": "2025-03-15T10:30:00Z",
    "date_range": "2024-12-15 – 2025-03-15",
    "source_article_ids": [
      "article-001",
      "article-002"
    ],
    "items": [
      {
        "date": "2025-03-15",
        "headline": "Trump announces new campaign strategy",
        "summary": "The former president outlined his approach to the 2024 race...",
        "significance": "primary subject",
        "source_article_id": "article-001"
      }
    ]
  }
}
```

---

## 4. PYTHON BACKEND: page_lookup.py

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/src/agents/page_lookup.py`

### Function: `_profile_to_text(profile: dict) -> str`

**Purpose:** Convert a profile dict to readable text for LLM evaluation

**Fields read from profile:**
- `profile.get("name")` — String
- `profile.get("bio")` — Object
  - Accesses: `bio.get("current_role")`, `bio.get("party")`
- `profile.get("notable_topics")` — Array (iterated)
  - For each topic, accesses: `topic.get("topic")`, `topic.get("category")`, `topic.get("stance")`, `topic.get("key_statements")`, `topic.get("evolution")`, `topic.get("controversies")`
  - `key_statements` is iterated: `for stmt in t["key_statements"]`
- `profile.get("controversies")` — Array (iterated)
  - For each controversy, accesses: `c.get("title")`, `c.get("year")`, `c.get("description")`
- `profile.get("relationships")` — Object
  - Accesses: `relationships.get("relationship_context")`

**Output format:** Formatted text suitable for LLM prompt (multiline string)

**Sample output:**
```
Name: Donald Trump
Role: Former President
Party: Republican

Notable Topics:

- Immigration [Policy]
  Stance: Restrictive enforcement
  Quote: We need to build a wall
  Quote: We have to secure our borders
  Evolution: Consistently hardline from 2015-present
  Controversies: Criticized for inflammatory rhetoric

Controversies:
- Access Hollywood tape (2005): Recording of Trump making lewd comments

Relationships: Has maintained rivalry with Clinton...
```

---

## 5. PROFILE ENRICHMENT: speaker_profile_enrichment.py

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/src/rss-extractor/src/services/speaker_profile_enrichment.py`

### Data Classes & Structure

#### RecentNewsItem (lines 117-143)
```python
@dataclass
class RecentNewsItem:
    date: str              # ISO 8601 date string
    headline: str          # Article headline
    summary: str           # ~200 chars summary of article
    significance: str      # Importance label (mapped from RelevanceLevel)
    source_article_id: str # doc_id of backing article
```

#### RecentNewsPayload (lines 145-171)
```python
@dataclass
class RecentNewsPayload:
    summary: str                      # Compact narrative summary
    last_updated: str                 # ISO 8601 timestamp
    date_range: str                   # "2025-01-01 – 2025-03-15"
    source_article_ids: list[str]     # Deduplicated list of doc_id values
    items: list[RecentNewsItem]       # Ordered list (newest first), capped at MAX
```

### Key Functions

#### `merge_profile_update(existing_profile, update)`
**Purpose:** Merge enrichment updates into existing profile

**Fields that are **ALWAYS** touched:
- `profile["recent_news"]` — Updated with new RecentNewsPayload

**Fields that are **CONDITIONALLY** touched:
- `profile["bio"]["current_role"]` — Updated only if `update.role_update.should_update` is True

**All other fields are preserved verbatim:**
- `bio.full_name`, `bio.born`, `bio.party`, `bio.net_worth_estimate`, `bio.previous_roles`, `bio.education`
- `controversies` (entire array)
- `media_profile`
- `relationships`
- `notable_topics`
- `dataset_insights`
- `public_perception`
- `timeline_highlights`

---

### Enrichment Configuration Constants (lines 60-77)
```python
MAX_RECENT_NEWS_ITEMS: int = 10        # Max items in recent_news.items
RECENT_NEWS_WINDOW_DAYS: int = 90      # Only keep news from last 90 days
MIN_ENRICHMENT_RELEVANCE_SCORE: float = 0.05  # Minimum score to trigger write
MIN_MATCH_CONFIDENCE: float = 0.7      # Minimum confidence for speaker match
HEADLINE_DEDUP_PREFIX_LEN: int = 60    # Characters used for dedup comparison
```

---

## 6. TEST FIXTURES (speaker_profile_enrichment_test.py)

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/src/rss-extractor/tests/test_speaker_profile_enrichment.py`

### Helper Functions

#### `_make_profile()`
Creates a test profile dict:
```python
profile = {
    "name": "Donald Trump",
    "bio": {
        "current_role": "President",
        "party": "Republican",
        "born": "1946",
    },
    "controversies": [],
    "media_profile": {},
    "relationships": {},
    "notable_topics": [],
    "dataset_insights": {"total_articles": 100},
    # ... other fields
}
```

#### `_make_record()`
Creates a SupabaseRecord (article):
```python
SupabaseRecord(
    id=1_000_001,
    doc_id="article-001",
    title="Test Headline",
    text="Article body text.",
    date="2025-03-01",
    media_name="Test News",
    media_type="rss_news",
    source_platform="rss",
    state="",
    city="",
    link="https://example.com/article",
    speakers_mentioned='{"Donald Trump"}',
    created_at="2025-03-01T12:00:00Z"
)
```

#### `_make_mention()`
Creates a PoliticianMention:
```python
PoliticianMention(
    politician_id="donald-trump",
    politician_name="Donald Trump",
    article_id="article-001",
    relevance=RelevanceLevel.PRIMARY,
    relevance_score=0.85,
    mention_count=5,
    matched_aliases=["Trump"],
)
```

---

## 7. API SERVICE: frontend/src/services/api.js

**File:** `/home/runner/work/Politics-Contradictor/Politics-Contradictor/frontend/src/services/api.js`

### Speaker-Related Methods

```javascript
async getSpeakers() {
  // GET /api/speakers
  // Returns array of speaker summary objects
  return axios.get('/api/speakers').then(r => r.data);
}

async getSpeakerProfile(speakerId) {
  // GET /api/speakers/{speakerId}
  // Returns full profile object
  return axios.get(`/api/speakers/${speakerId}`).then(r => r.data);
}
```

---

## 8. SIDEBAR SPEAKER LIST DATA STRUCTURE

**Used in SpeakerProfile.jsx (lines 306-316)**

Data returned from `GET /api/speakers`:
```json
[
  {
    "speaker_id": "donald_trump",
    "name": "Donald Trump",
    "party": "Republican",
    "current_role": "Former President",
    "born": "1946",
    "total_articles": 1250
  }
]
```

**Fields accessed:**
- `s.speaker_id` — Used as React key and for API call
- `s.name` — Displayed in sidebar
- `s.party` — Displayed as meta
- `s.total_articles` — Displayed with `.toLocaleString()`

---

## Summary Table: Profile Fields by Component

| Component | Top-Level Key | Fields Accessed | Type | Conditional |
|-----------|---|---|---|---|
| Bio | `bio` | full_name, born, party, current_role, net_worth_estimate, previous_roles[], education[] | Object + Arrays | Yes |
| Notable Topics | `notable_topics` | topic, category, stance, key_statements[], evolution, controversies | Array | Yes |
| Timeline | `timeline_highlights` | year, event, significance | Array | No |
| Controversies | `controversies` | title, year, description, outcome, impact | Array | Yes |
| Relationships | `relationships` | allies[], opponents[], co_mentioned_figures{}, relationship_context | Object + Arrays | Yes |
| Perception | `public_perception` | approval_trend, base_support, opposition, key_narratives[] | Object + Array | Yes |
| Media | `media_profile` | coverage_volume, top_covering_states{}, media_narrative, sentiment_trend | Object | Yes |
| Insights | `dataset_insights` | total_articles, date_range, top_title_keywords{}, geographic_focus | Object | Yes |

---

## Key Takeaways

1. **All profile data flows through these channels:**
   - API `/api/speakers/<id>` returns the full profile JSON from the database
   - React components read specific nested fields with optional chaining (`?.`) and fallbacks
   
2. **Array fields expect specific object shapes:**
   - `bio.previous_roles` and `bio.education`: Arrays of strings
   - `notable_topics`: Objects with `topic, category, stance, key_statements[], evolution?, controversies?`
   - `timeline_highlights`: Objects with `year, event, significance`
   - `controversies`: Objects with `title, year, description, outcome?, impact?`
   - `relationships.allies/opponents`: Arrays of strings
   - `relationships.co_mentioned_figures`: Object with string keys and numeric values
   - `public_perception.key_narratives`: Array of strings
   - `media_profile.top_covering_states`: Object with string keys and numeric values
   - `dataset_insights.top_title_keywords`: Object with string keys and numeric values

3. **Enrichment only updates two fields:**
   - `profile.recent_news` — Always updated
   - `profile.bio.current_role` — Conditionally updated when role evidence exists

4. **Recent news has its own structure:**
   - Max 10 items, newest first
   - Auto-expires after 90 days
   - Deduplicates by headline prefix matching
