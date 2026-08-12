# Sierra Outfitter Agent

Sierra Outfitters is an emerging outdoor retailer competing with brands like Patagonia, Cotopaxi, and REI. This repo is a simple localhost chat agent with order lookup, product recommendations, and Early Risers promotions.

## Prerequisites

- Python 3.12+
- Node.js 20+ (22.12+ recommended; Vite 5 works on older 22.x)
- OpenAI API key in `.env`:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

## Quick start

**Option A — one script (both servers):**

```bash
chmod +x start.sh
./start.sh
```

**Option B — two terminals:**

```bash
# Terminal 1 — API
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server.main:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — UI
cd frontend
npm install
npm run dev
```

Open **http://127.0.0.1:5173** (UI proxies `/api` and `/assets` to the backend).

## Try it

- **Order status:** “What's the status of order #W001?”
- **Product recs:** “Recommend gear for hiking”
- **Early Risers:** “I'd like the Early Risers Promotion” (codes only 8:00–10:00 AM Pacific)
- **Image:** attach a photo with the + button in the composer

## Evaluation Suite (`evals/`)

Automated evaluation testing framework covering all three core agent functionalities:

1. **Catalog Search (`search_catalog`)**: Gear Q&A, recommendations, tag filtering, and stock availability.
2. **Customer Orders (`lookup_order`)**: Order status, tracking numbers, and USPS tracking links by order number or email.
3. **Early Risers Discount (`early_riser_promo`)**: Time-window validation (8:00–10:00 AM Pacific) and explicit promo request guardrails.

**Run full evaluation suite:**
```bash
.venv/bin/python -m evals.eval_runner
```

**Run category-specific evals:**
```bash
.venv/bin/python -m evals.eval_runner --category catalog
.venv/bin/python -m evals.eval_runner --category order
.venv/bin/python -m evals.eval_runner --category promo
```

**Run using Pytest:**
```bash
.venv/bin/pytest evals/
```

## Unit Testing (`tests/`)

Fast, deterministic unit tests for internal tools (`lookup_order`, `search_catalog`, `early_riser_promo`), system prompt builders, and FastAPI API endpoints:

```bash
.venv/bin/pytest tests/
```

| Suite | Focus | Command |
|---|---|---|
| `tests/test_tools.py` | Order lookups, catalog ranking, tag filtering, stock checks, promo windows | `.venv/bin/pytest tests/test_tools.py` |
| `tests/test_api.py` | FastAPI endpoints (`/api/health`, `/api/history`, `/api/reset`, `/api/chat`, `/assets`) | `.venv/bin/pytest tests/test_api.py` |
| `tests/test_prompts.py` | System prompt builder and brand voice validation | `.venv/bin/pytest tests/test_prompts.py` |

## Repository structure

| Path | Purpose |
|---|---|
| `server/` | FastAPI app, agent loop, tools |
| `frontend/` | React chat UI |
| `evals/` | Evaluation suite, dataset, and runner |
| `customer_profile` | Brand voice & guardrails |
| `product_catalog.json` | Static product dataset |
| `customer_order.json` | Static order dataset |
| `assets/` | Product images |
| `.env` | API key & model |

## How it works

1. Browser stores only a `session_id`; all chat history lives in server memory.
2. Each message hits `POST /api/chat`; the agent loop calls OpenAI with up to 25 prior turns.
3. The model can invoke tools (`lookup_order`, `search_catalog`, `early_riser_promo`); results go back to the model until it replies in plain text.
4. Product recommendations return structured JSON for the horizontal carousel in the UI.

## Notes

- Server memory resets on restart (fine for localhost).
- Run a single uvicorn worker — no Redis/DB needed for this demo.

