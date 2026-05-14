# Story Pattern Lab Development Directives

## 1. Core Product Direction

Story Pattern Lab is a viral story discovery and production system for overseas and domestic story-based content.

The product should evolve from a simple Streamlit prototype into a production workflow that supports:

1. real-time data scoring,
2. source-specific data lists for domestic and overseas platforms,
3. post overview panels with original text and Korean translation,
4. score leaderboards,
5. production material confirmation,
6. LLM inference, analysis, and safe rewriting principles,
7. 10-minute longform script generation,
8. expansion into Shorts, Threads, and card-news production environments.

## 2. Required Dashboard Structure

### 2.1 Real-Time Data Score

The dashboard must support real-time or near-real-time scoring based on repeated metric snapshots.

Required metrics:

- collected_at
- posted_at
- source
- platform
- rank_position
- like_count or score
- comment_count
- view_count when available
- comments_per_hour
- score_per_hour
- velocity_score
- debate_score
- viral_score
- risk_score

Current RSS-only collection is not enough. The system must evolve toward API-based metric collection and repeated snapshots.

### 2.2 Site-Specific Data Lists

Dashboard should separate data by source group.

Domestic source groups:

- DCInside
- Nate Pann
- Blind, if legally and technically viable
- FMKorea
- TheQoo
- Instiz
- Naver Cafe or blog sources, only when policy allows

Overseas source groups:

- Reddit AITA
- Reddit relationship_advice
- Reddit TrueOffMyChest
- Reddit BestofRedditorUpdates
- Reddit EntitledParents
- Reddit antiwork
- Reddit wedding-related communities
- Other public RSS/API sources

Each source must have:

- source_name
- source_url
- source_type
- country_group: domestic or overseas
- collection_method
- policy_risk_level
- is_active

### 2.3 Row Click Detail Panel

When a user clicks a row in the dashboard, the app should show a detail panel.

Required panel content:

- source and URL
- collected_at
- posted_at
- current metrics
- score breakdown
- original text or excerpt, when legally and technically allowed
- Korean translation
- short summary
- core conflict
- character relationship map
- red flags
- debate point
- audience emotion
- risk notes
- production recommendation

Original text should not be stored blindly. If the site policy is risky, the app should store only a short excerpt or fetch-on-demand summary.

### 2.4 Score Leaderboard

Dashboard must include leaderboards.

Required leaderboards:

- Viral Score TOP 50
- Velocity Score TOP 50
- Debate Density TOP 50
- Shorts Potential TOP 50
- Longform Potential TOP 50
- Low Risk + High Viral TOP 50
- Domestic TOP 50
- Overseas TOP 50

### 2.5 Production Material Confirmation

The workflow must include a stage where the operator confirms whether a story becomes production material.

Status values:

- collected
- analyzed
- candidate
- approved
- scripted_longform
- expanded_shorts
- expanded_threads
- expanded_cardnews
- rejected
- archived

The dashboard should allow the user to mark a post as:

- production candidate
- approved material
- rejected
- needs legal/risk review

## 3. LLM Inference and Rewriting Principles

### 3.1 LLM Analysis Layer

The LLM should infer:

- story summary
- core conflict
- emotional trigger
- hidden relationship pattern
- red flag structure
- timeline
- role of each character
- why the audience will react
- comment trigger
- cultural localization notes
- risk factors

### 3.2 Original Text Handling

Principles:

- Do not blindly copy the source text.
- Avoid storing large volumes of original comments.
- Remove or generalize names, schools, workplaces, addresses, account IDs, and other identifying details.
- Convert source material into analysis notes and a new script structure.
- The final script should be a transformed, original narration, not a translated copy.

### 3.3 Korean Translation

The detail panel should support Korean translation for the operator.

Translation should be for internal production understanding, not necessarily for final publication.

### 3.4 Reprocessing / Rewriting Principle

The app should apply this order:

```text
Original post or excerpt
↓
Korean translation for operator
↓
LLM inference analysis
↓
risk filtering and de-identification
↓
story structure reconstruction
↓
10-minute longform script
↓
shorts / threads / card-news expansion
```

## 4. Script Generation Environment

### 4.1 Main Longform Script

Primary output should be a 10-minute YouTube script.

Required structure:

1. Cold open
2. Context setup
3. First red flag
4. Escalation
5. Turning point
6. Hidden pattern analysis
7. Emotional climax
8. Comment-triggering question
9. Closing line

The tone should target overseas storytime viewers. The script should use natural English unless otherwise configured.

### 4.2 Shorts Expansion

From the longform script, generate:

- 30-second shorts
- 60-second shorts
- 90-second shorts
- title options
- thumbnail text
- caption text
- comment question

### 4.3 Threads Expansion

From the longform script, generate:

- 5-post thread
- 10-post thread
- punchline version
- controversy version
- question-led version

### 4.4 Card-News Expansion

From the longform script, generate:

- 6-card version
- 8-card version
- 10-card version
- each card title
- each card body
- image prompt
- design note

## 5. Development Priority

### Phase 1: Streamlit Dashboard Upgrade

- Add source group selector: domestic / overseas
- Add collected_at and posted_at display
- Add freshness indicator
- Add score leaderboards
- Add row detail panel
- Add material status selection

### Phase 2: Better Collection

- Add Reddit API collector
- Add metric snapshots
- Add velocity calculation
- Add source registry
- Add basic domestic source registry without risky crawling first

### Phase 3: LLM Analysis

- Add post overview generation
- Add Korean translation
- Add inference analysis
- Add risk filtering
- Add production recommendation

### Phase 4: Production Generator

- Add 10-minute longform script generator
- Add Shorts expansion
- Add Threads expansion
- Add Card-news expansion

### Phase 5: Persistence and Deployment

- Add DB or lightweight local storage
- Add Streamlit Cloud deployment
- Later migrate to FastAPI + Next.js if needed

## 6. Current Working Rule

Since the user is a development beginner and wants ChatGPT to edit GitHub directly, the user should only test the Streamlit app in the browser and provide feedback. ChatGPT handles code changes in GitHub.
