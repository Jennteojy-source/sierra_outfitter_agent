# Sierra Outfitter Agent

Sierra Outfitters is an AI-powered retail assistant for an outdoor gear brand. It features order lookup, product catalog search with recommendations, and an Early Risers discount promotion.

## Prerequisites

Add your OpenAI API key to `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

---

## Commands

### 1. Start (Server + UI)

Start both the FastAPI backend (`http://127.0.0.1:8000`) and React frontend (`http://127.0.0.1:5173`):

```bash
./start.sh
```

### 2. Run Tests (Unit Tests)

Run fast, deterministic unit tests for tools, prompt construction, and API endpoints:

```bash
.venv/bin/pytest tests/
```

### 3. Run Evals (LLM Agent Evaluation)

Run automated evaluation test suite testing end-to-end agent tool usage, argument extraction, and promo guardrails:

```bash
.venv/bin/python -m evals.eval_runner
```

---

## Features

- **Catalog Search (`search_catalog`)**: Gear Q&A, tag filtering, stock availability checks, and product recommendations.
- **Customer Orders (`lookup_order`)**: Order status, item breakdowns, and USPS tracking link generation by order number or email.
- **Early Risers Discount (`early_riser_promo`)**: Time-bound 10% discount codes valid only between 8:00 AM – 10:00 AM Pacific Time when explicitly requested.

---

## Repository Structure

| Path | Purpose |
|---|---|
| `server/` | FastAPI server, OpenAI agent loop, and tools |
| `frontend/` | React chat UI |
| `tests/` | Unit test suite for tools, prompts, and endpoints |
| `evals/` | LLM evaluation suite, dataset, and runner |
| `customer_profile` | Brand voice & guardrail instructions |
| `product_catalog.json` | Product inventory dataset |
| `customer_order.json` | Order tracking dataset |
| `assets/` | Product images |
| `start.sh` | One-command starter script |
