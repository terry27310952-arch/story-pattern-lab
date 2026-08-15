# Crypto Trader Briefing Architecture

This app generates Japanese crypto editorial carousels for `勢力ハンター キヨサキ`.
The v13 architecture keeps facts deterministic and lets reasoning engines make
editorial decisions only.

## Pipeline

```text
SOURCE COLLECTION
-> SOURCE NORMALIZATION / CLUSTERING
-> CANONICAL MARKET SNAPSHOT
-> CANONICAL EVIDENCE STORE
-> MARKET REASONING
-> MASTER CAROUSEL DIRECTOR
-> CARD COPY DIRECTOR
-> JA EDITORIAL LOCALIZER
-> VISUAL DIRECTOR
-> IMMUTABLE DATA RECONCILIATION
-> SEMANTIC / DATA / JA QA
-> FINAL VARIANT BUILDER
-> BRAND OUTRO APPEND
-> RENDER / EXPORT
```

## Data Authority

The code owns all market numbers, source URLs, timestamps, source IDs, and
evidence identities. `market_summary` is always derived from `market_snapshot`
by `summarize_market()`. External reasoning output may never become the source
of truth for:

- BTC price, support, resistance, MA, RSI, MACD, ATR
- funding, mark price, open interest
- Fear & Greed, BTC dominance, ETH/BTC, TOTAL2, TOTAL3
- publisher, article URL, source ID, posted/collected timestamps

After every reasoning pass, cards are reconciled against canonical metrics,
canonical sources, and canonical evidence references.

## Reasoning Contract

Reasoning stages return patches, not whole replacement cards.

- `carousel_plan`: `card_id`, `card_type`, `angle`, `priority`,
  `evidence_refs`, `justification`
- `card_copy`: `card_id` plus visible copy fields only
- `ja_localization`: `card_id` plus localized visible copy only
- `visual_direction`: `card_id` plus predefined visual direction fields only

`merge_stage_patch()` ignores fields outside the stage whitelist.

## Evidence Gate

Each analysis card must have direct evidence. Weak cards are removed instead of
being used to fill a quota. If fewer than five content cards qualify, the app
records `content_shortage_reason` and still appends the locked brand outro.

News cards require a source reference with source quality metadata. Reaction
claims are limited unless price reaction data is available.

## Global Context

`collect_market_snapshot()` includes `global_context`:

- `btc_dominance` from public crypto global data when available
- `eth_btc` calculated as ETH spot price / BTC spot price
- `total_market_cap`
- `TOTAL2 = total crypto market cap - BTC market cap`
- `TOTAL3 = total crypto market cap - BTC market cap - ETH market cap`

Missing data remains `null`; the app does not invent zero values.

## Japanese Localization

Production locale defaults to `ja-JP`. Japanese copy is editorialized from the
semantic model and locked data, not translated from Korean prose. QA checks
empty placeholders, Korean text leakage, translationese patterns, and internal
field labels.

## Observer Visual System

The Observer identity is immutable:

- faceless adult male
- black suit, black shirt, black tie, black leather gloves
- face fully hidden, no eyes, nose, mouth, or expression
- orange rim light
- near-black institutional briefing environment

The visual director can vary shot, pose, camera, position, visibility, layout,
negative space, and hierarchy. Pixel coordinates stay inside renderer rules.
Preview uses `assets/brand/observer_reference.png`; missing pose assets are
shown as production specifications, not as generated images.

## Renderer And QA

The current app exposes an `Editorial Preview` and a `Production Render Spec`.
Japanese text, metrics, chart labels, and source labels are composited by the
renderer/export layer, not generated inside background images.

QA severities:

- `INFO`: diagnostic metadata
- `WARNING`: repairable or non-blocking variation issues
- `BLOCKING`: empty variable, fake source, numeric mismatch, evidence failure,
  missing brand outro, or non-renderable card

Non-renderable analysis cards are excluded from production preview, Markdown,
JSON, and Excel outputs. Debug cards can be inspected separately in the UI.

## Legacy Isolation

Story Pattern Lab script-improvement modules are preserved under
`legacy/story_pattern_lab/` and are no longer mounted in the production
Streamlit pages namespace.
