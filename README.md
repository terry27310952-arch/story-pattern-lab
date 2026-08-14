# Japan Crypto Pattern Lab

Japan Crypto Pattern Lab is a Streamlit radar for Japanese crypto community
signals, Japanese crypto media, CoinMarketCap-style global headlines, and
publishable card news / Note content.

The first version starts with Streamlit so the full product flow can be tested quickly:

1. Collect crypto candidates from Japanese and global RSS sources.
2. Pull public-list signals from 5ch's crypto board and CoinMarketCap headlines.
3. Sort them with freshness, community reaction, and production scores.
4. Classify each item as BTC, altcoin, regulation, exchange, security, macro, or Web3.
5. Repurpose selected issues into shorts, Threads, card news, and Note content.

The OpenAI-backed production flow defaults to `gpt-5.5` for richer issue
analysis, longform script generation, and derivative content packages for card
news and Note publishing. You can override it with the `OPENAI_MODEL`
environment/Streamlit secret.

## Local Streamlit Test

```cmd
cd apps\streamlit
pip install -r requirements.txt
streamlit run app.py
```

Open:

```text
http://localhost:8501
```

## Current Development Policy

- This repository is separated from `ai-pd-studio` to avoid confusion.
- Start with Streamlit only.
- Add exchange APIs, market data, DB storage, FastAPI, and Next.js later.
