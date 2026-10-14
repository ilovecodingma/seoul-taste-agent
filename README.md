# Seoul Taste Agent

Qloo Agentic Hackathon entry. An agent that turns a traveller's tastes (artists, films, shows, books) into a one-day Seoul route, using Qloo's Taste AI as the only source of "what fits you".

## How it works

1. `parse_tastes` extracts cultural items from free text (optional LLM, deterministic fallback).
2. `QlooClient.search` resolves each item to a Qloo entity ID.
3. For each of 8 Seoul districts, `QlooClient.insights` (`filter.type=urn:entity:place`, `filter.location.query`, `signal.interests.entities`) returns taste-ranked places with affinity.
4. Districts are ranked by mean affinity; the top two fill morning/afternoon/evening/late-night slots.
5. The UI shows the route, the neighborhood scores and the full tool-call trace.

Without Qloo, the agent has nothing to rank with: the matching is the Qloo call.

## Run

```
python -m unittest discover -s tests -t .
QLOO_API_KEY=... python -m app.server      # http://localhost:8080
```

Without `QLOO_API_KEY` the server starts in a clearly labelled offline simulation (synthetic data, not Qloo data) for development. Optional `ANTHROPIC_API_KEY` enables LLM parsing/narration.

Deploy: `Dockerfile` runs on any container host (Render, Fly.io, Hugging Face Spaces). Set `QLOO_API_KEY` as a host secret; the key never reaches the browser. Requests are rate-limited per IP to protect quota.

## Responsible use

Results are aggregate affinities, not facts about a person. No personal data is sent to Qloo. No Qloo response data is stored in this repository.

License: MIT
