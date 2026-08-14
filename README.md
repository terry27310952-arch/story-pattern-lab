# Crypto Trader Briefing Lab

Streamlit app for collecting Japanese crypto media, Japanese community signals,
CoinMarketCap-style headlines, and free market context, then turning selected
resources into trader-facing briefings, card news, Note content, and Excel
packages.

## Core Flow

1. Collect resources from Japanese crypto RSS, public news lists, 5ch crypto
   board subjects, CoinMarketCap headlines, and Yahoo Finance Japan lists.
2. Refresh market context for Bitcoin, major alts, Nikkei 225, gold, Nasdaq,
   DXY, US 10Y yield, and crypto sentiment.
3. Multi-select resources for a briefing bundle.
4. Generate either:
   - weekly direction briefing around BTC, Nikkei, gold, alts, asset rotation,
     and market regime
   - daily time-zone briefing around Bitcoin-related catalysts and reactions
5. Split the briefing into card news sets: 5 slides, 6 slides, 7 slides, and a
   custom AI suggestion.
6. Export Markdown, JSON, and `.xlsx` files with separate sheets for briefing,
   card news, Note, sources, and market data.

## Free Reasoning Options

The app works without a paid API key by using its built-in local reasoning
engine. That default engine is deterministic and always available.

Optional external reasoning backends:

- Ollama local model
  - `OLLAMA_BASE_URL=http://localhost:11434`
  - `OLLAMA_MODEL=qwen3:4b`
- OpenAI-compatible free-tier endpoint
  - `FREE_AI_API_BASE=https://example.com/v1`
  - `FREE_AI_MODEL=free-reasoning-model`
  - `FREE_AI_API_KEY=...`

If an external backend fails, the app falls back to the local reasoning engine.

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
