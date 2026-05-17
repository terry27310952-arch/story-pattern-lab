# Story Pattern Lab

Story Pattern Lab is a beginner-friendly viral story radar for overseas storytime content.

The first version starts with Streamlit so the full product flow can be tested quickly:

1. Collect story candidates from public RSS sources.
2. Sort them with a basic viral score.
3. Classify story angles.
4. Generate a first shorts script draft.

The OpenAI-backed production flow defaults to `gpt-5.5` for richer story
analysis, live counseling structure, and longform script generation. You can
override it with the `OPENAI_MODEL` environment/Streamlit secret.

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
- Add Reddit API, LLM generation, DB storage, FastAPI, and Next.js later.
