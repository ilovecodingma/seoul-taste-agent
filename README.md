# Seoul Taste Agent

Qloo Agentic Hackathon entry. An agent that turns a traveller's tastes (artists, films, shows, books) into a one-day Seoul route, using Qloo's Taste AI as the only source of "what fits you".

## How it works

1. `parse_tastes` extracts cultural items from free text (optional LLM, deterministic fallback).
2. For each of 8 Seoul districts the agent calls the official Qloo harness: `qloo exec recommend` with `target_type=place`, `signals=[your tastes]`, `filter_location=<district>`, explainability on. Qloo itself resolves the names to entities; unmatched names (`needs_input`) are dropped and retried.
3. Districts are ranked by mean affinity; the top two fill morning/afternoon/evening/late-night slots.
4. The UI shows the route, neighborhood scores and the full tool-call trace.

Without Qloo the agent has nothing to rank with: the matching is the Qloo call.

## Run

Requirements: Python 3.10+, Node.js 22.19+ and `npm install --global @qloo/qloo-harness` (the event-supported route; serverless/browser calls are not supported).

```
python -m unittest discover -s tests -t .
export QLOO_API_KEY=...        # event key, server-side only
python scripts/live_check.py   # one real call
python -m app.server           # http://localhost:8080
```

The hackathon key only works against `https://hackathon.api.qloo.com` (set automatically; override with `QLOO_BASE_URL`). Without `QLOO_API_KEY` the server starts in a clearly labelled offline simulation (synthetic data, not Qloo data). Optional `ANTHROPIC_API_KEY` enables LLM parsing/narration.

Deploy: the `Dockerfile` (Node + harness + Python) and `render.yaml` target Render; set `QLOO_API_KEY` as a secret. Requests are rate-limited per IP to protect quota.

## Responsible use

Results are aggregate affinities, not facts about a person. No personal data is sent to Qloo. No Qloo response data is stored in this repository.

License: MIT
