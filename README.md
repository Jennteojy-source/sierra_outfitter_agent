# Sierra Outfitters Agent

Retail chat agent for Sierra Outfitters: catalog recommendations, order status and tracking, and the Early Risers promotion. Built as a hand-written OpenAI tool loop (no agent framework).

## Prerequisites

- Python 3
- Node.js (`npm`)
- An OpenAI API key in `.env` at the repo root:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

`.env` is gitignored. `./start.sh` creates `.venv` and installs frontend deps on first run.

## Commands

### 1. Start (API + UI)

```bash
./start.sh
```

- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:5173`

### 2. Unit tests

Deterministic tests for tools, prompts, and API endpoints (no live OpenAI calls):

```bash
.venv/bin/pytest tests/
```

### 3. Evals

Live LLM evals for tool choice, arguments, promo eligibility, and multi-turn order lookup:

```bash
.venv/bin/python -m evals.eval_runner
```

## Features

- **Catalog (`search_catalog`)**: Recommendations, stock, and tags from `product_catalog.json`. Honest misses — no invented products.
- **Orders (`lookup_order`)**: Status, items, and a USPS tracking URL. Requires **both** order number and email from `customer_order.json`. Tracking link: `https://tools.usps.com/go/TrackConfirmAction?tLabels={trackingNumber}`.
- **Early Risers (`early_riser_promo`)**: Unique 10% code. The tool decides eligibility: the customer must ask for Early Risers by name, and the clock must be 8:00–10:00 AM Pacific. Generic coupon asks do not mint a code.
- **Handoff (`request_human_handoff`)**: Queues a human for refunds, billing, and other out-of-scope issues. The agent can still help with catalog, orders, and Early Risers while they wait.

## Repository Structure

| Path | Purpose |
|---|---|
| `server/` | FastAPI app, OpenAI tool loop, prompts, and tools |
| `frontend/` | React chat UI |
| `tests/` | Unit tests |
| `evals/` | Live LLM eval dataset and runner |
| `customer_profile` | Brand voice |
| `product_catalog.json` | Catalog dataset |
| `customer_order.json` | Order dataset |
| `assets/` | Product images |
| `start.sh` | One-command starter |
