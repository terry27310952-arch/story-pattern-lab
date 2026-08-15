# Crypto Trader Briefing Lab

Streamlit app for collecting Japanese and global crypto media, Japanese
community signals, CoinMarketCap/Yahoo Finance public headline lists, and live
market context, then turning selected full-text resources into trader-facing
briefings, card news, Note content, and Excel packages for the Japanese
editorial brand `勢力ハンター キヨサキ`.

## Core Flow

1. Collect resources from Japanese crypto RSS, global crypto RSS, public news
   lists, 5ch crypto board subjects, CoinMarketCap headlines, and Yahoo Finance
   Japan lists.
2. Refresh market context for Bitcoin, major alts, Nikkei 225, gold, Nasdaq,
   DXY, US 10Y yield, and crypto sentiment.
3. Derive BTC/major-alt price levels from daily OHLC: 24H/7D/30D/90D
   highs/lows, MA20/50/100/200, Bollinger bands, 90D Fibonacci levels, and
   round-number pivots.
4. Add technical and derivatives data: RSI14, MACD, ATR14, 20D average volume,
   Binance Futures funding rate, mark price, and open interest.
   - If Binance daily candles are unavailable, the app falls back to CoinGecko
     `market_chart` daily data so briefing text does not degrade to empty
     price-level or indicator fields.
   - Derivatives data uses Binance Futures first, then fills missing mark
     price, funding, and open-interest fields from Bybit and OKX public APIs.
5. Multi-select resources for a briefing bundle.
6. Fetch every selected article body where public access is possible. Community
   items are treated as sentiment signals only and do not store comment bodies.
7. Generate either:
   - weekly direction briefing around BTC, Nikkei, gold, alts, asset rotation,
     and market regime
   - daily time-zone briefing around Bitcoin-related catalysts and reactions
8. Apply a professional BTC-first analysis lens inspired by
   `https://www.youtube.com/@bitcoinilluminati`: BTC structure first, alts as
   downstream rotation, chart invalidation before conviction, and sentiment as
   a secondary signal.
9. Generate a subjective `trader_stance` layer: directional bias, preferred
   posture, conviction score, expected price path, entry plan, profit plan,
   risk/invalidation, no trade zone, alt strategy, and personal trading
   philosophy.
   The same first-person trader perspective is embedded directly into
   scenarios, weekly notes, and daily time-zone notes so the output reads like
   a personal market view rather than a list of collected facts.
   Daily notes are written as time-zone interpretation essays with expected
   move, action plan, and no-trade criteria.
10. Convert the briefing into production-ready editorial carousel sets through
    a four-layer pipeline:
    - `DATA`: lock current price, support, resistance, rates, MA, RSI, MACD,
      ATR, funding, open interest, Fear & Greed, BTC dominance, ETH/BTC,
      source, URL, generation date, and timeframe.
    - `REASONING/EDITORIAL`: choose important signals, score evidence, remove
      weak or overlapping card candidates, and plan the carousel narrative.
    - `LOCALIZATION/VISUAL DIRECTION`: create Japanese-native editorial copy
      and choose vertical layout, character shot, pose, camera, and hierarchy.
    - `RENDERER`: display only final user-facing card text, metrics, sources,
      and renderer-composited Japanese typography.
    Supported card types are fixed to `market_conclusion`, `key_levels`,
    `derivatives`, `news_context`, `scenarios`, `trade_plan`, and
    `brand_outro`.
    The visual layer is branded around `The Observer`: a faceless anonymous
    market observer in black suit, black shirt, black tie, black leather gloves,
    and warm orange rim light. Cards are vertical-first for 4:5
    `1080x1350` and 9:16 `1080x1920`, not square layouts stretched vertically.
    Image prompts never ask the image model to render long Japanese text; the
    renderer composites copy, metrics, chart labels, and sources. Every set ends
    with a locked `brand_outro` card:
    `勢力ハンター キヨサキ` / `フォローして、勢力が入ったポイントを無料でチェック。`
11. Export Markdown, JSON, and `.xlsx` files with separate sheets for briefing,
    source findings, scenarios, card news, Note, sources, market data, price
    levels, indicators, derivatives, and trader stance. Card sheets use the
    final schema: `card_type`, `eyebrow`, `headline`, `subheadline`,
    `key_message`, `metrics`, `insight`, `action`, `risk`, `visual_direction`,
    and `source`. The Excel package also includes `Visual_Direction`, with
    layout variant, character shot, character visibility, 4:5 prompt, 9:16
    prompt, and negative prompt.
12. Build Note content as a publishable trader note with content metadata, BTC
    data map, derivatives/indicator read, source-by-source interpretation,
    Bull/Base/Bear scenarios, weekly/daily operating notes, card-news conversion
    guide, posting copy, and risk conditions.

## Free Reasoning Options

The app works without a paid API key by using its built-in deterministic rule
engine. That default path is fast, free, and always available as a safe
fallback. Deeper editorial reasoning can be connected through a local Ollama
model or an OpenAI-compatible inference endpoint.

Optional external reasoning backends:

- Ollama local model
  - `OLLAMA_BASE_URL=http://localhost:11434`
  - `OLLAMA_MODEL=qwen3:4b`
- OpenAI-compatible free-tier endpoint
  - `FREE_AI_API_BASE=https://example.com/v1`
  - `FREE_AI_MODEL=free-reasoning-model`
  - `FREE_AI_API_KEY=...`

If an external backend fails, the app falls back to the deterministic rule
engine without crashing the production card/export flow.

## Architecture Notes

See `docs/crypto-trader-briefing-architecture.md` for the v13 canonical data,
reasoning patch, evidence gate, Japanese localization, Observer visual, QA, and
legacy isolation contracts.

## Local Streamlit Test

```cmd
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Open:

```text
http://localhost:8501
```

## Deployment Entry Point

Use this file in Streamlit Community Cloud:

```text
streamlit_app.py
```
