# Sierra Outfitters Agent

Multimodal retail chat agent for Sierra Outfitters. Handles order tracking, product recommendations (text + image), Early Risers promotions, human handoff, and a one-time idle nudge.

## Product overview

A trail-guide chat that stays in retail scope: catalog, orders, and Early Risers. Out-of-scope issues (refunds, billing, claims) queue a human while the agent keeps helping with what it can. Sessions remember multi-turn context until **Reset**.

### Features

- **Catalog (`search_catalog`)**: Text and image-based recommendations from `product_catalog.json`. Honest misses — no invented products.
- **Orders (`lookup_order`)**: Status, items, and a USPS tracking URL. Requires **both** order number and email from `customer_order.json`.
- **Early Risers (`early_riser_promo`)**: Unique 10% code. Tool-enforced: must ask for Early Risers by name, and only valid 8:00–10:00 AM Pacific.
- **Handoff (`request_human_handoff`)**: Queues a human for refunds / billing / out-of-scope issues. Agent stays available for in-scope help while waiting.
- **Idle nudge**: One-time check-in after idle (see `NUDGE_IDLE_SECONDS`).
- **Session memory**: Same chat keeps history across turns until **Reset**.

---

## Design decisions

### Agent loop

- **Hand-written OpenAI tool loop (no agent framework)**: A small custom loop in `server/agent.py` — clearer control over history, tool caps, and debug traces for a demo-sized system.
- **Policy in tools, not just the prompt**: Early Risers eligibility and “both order # + email” are enforced in tool code so the model cannot soft-bypass them. Prompts steer; tools gate.
- **Live Pacific clock in the system prompt**: Injected PT timestamp each turn so Early Risers uses wall-clock time, not the model’s guess.
- **Vision → search, don’t invent from the photo**: Look at the upload, then call `search_catalog`. Names, SKUs, and stock come from tools only.
- **Structured product cards**: Carousel data is returned from `search_catalog` for the UI; assistant replies stay plain text (no markdown product dumps).
- **Assortment overview is orientation only**: The prompt summarizes categories/tags for routing; every concrete product claim still requires `search_catalog`.
- **Context hygiene**: History is trimmed (~25 messages, without orphaning tool turns) and older images are dropped so base64 uploads cannot blow the context window.
- **Nudge is a separate, tool-less one-shot**: Lighter prompt, no catalog/order calls, once per session until **Reset**. Idle nudge is also suppressed after handoff.

### Chat UX

- **Optimistic delivery**: On send, the user bubble (and image preview) appears immediately; the reply is appended when the API returns. On failure, the optimistic bubble is rolled back and the draft is restored.
- **Grey / disabled composer while waiting**: Send, attach, and the textarea are disabled until the agent finishes — avoids double-sends and overlapping turns. A “Scouting the trail…” placeholder shows progress.
- **Handoff is a queue, not a mute**: After `request_human_handoff`, chat stays open for in-scope help (orders, catalog, Early Risers). The banner and placeholder make that clear. Only the **idle nudge** is suppressed while a human is queued.

### Data & sessions

- **JSON as the source of truth**: Catalog and orders live in `product_catalog.json` / `customer_order.json` — mock data, no real DB for this demo.
- **In-memory search index**: Built once at load from the catalog (`catalog_index.py`) so `search_catalog` does token lookup instead of rescanning every field per query.
- **In-memory sessions**: Conversation history, UI messages, and flags (`handed_off`, `nudged`, `rated`) are process-local dicts. Fine for a single-server demo; **Reset** starts a fresh session id and clears that memory.

### Developer mode & instrumentation

- **Debug on**: Per assistant turn, shows model, tool names + args, token usage, API call count, and estimated cost.
- **Reset**: Clears server session history / meta and gives the UI a new session — use between demo scenarios so memory does not leak across flows.
- **Tests vs evals**: Fast unit tests cover API/tools/prompts; `evals/` runs live multi-turn LLM checks against the real catalog and order rules.

---

## Technology

### Backend

| Piece | Choice |
|---|---|
| API | FastAPI + Uvicorn |
| Agent | OpenAI Chat Completions tool loop (`openai` Python SDK) |
| Model | `OPENAI_MODEL` (default `gpt-4o`) |
| Data | Static JSON + in-memory inverted catalog index |
| Sessions | In-process dicts (per `X-Session-Id`) |
| Config | `python-dotenv` (`.env`) |

### Frontend

| Piece | Choice |
|---|---|
| UI | React 19 |
| Bundler | Vite |
| API | `fetch` to FastAPI (`/api/chat`, `/api/nudge`, `/api/reset`, …) |

### Tooling

| Piece | Choice |
|---|---|
| Unit tests | `pytest` |
| Live evals | `evals/eval_runner.py` against the real model |
| Start | `./start.sh` (API on `:8000`, UI on `:5173`) |

---

## Future improvements

### Streaming UX

- Stream assistant tokens (and optionally tool-start events) over SSE/WebSockets so the UI paints immediately instead of waiting for the full tool loop.
- Keep optimistic user bubbles; replace the “Scouting the trail…” placeholder with partial text + cancel-in-flight.

### Agent frameworks (LangGraph / Agents SDK / LangChain)

- Move from the hand-written loop to a framework when workflows need **durable runs**, **retries**, and **human-in-the-loop interrupts** (pause on refund/handoff, resume when a trail guide joins).
- Use checkpointed state so conversations survive deploys and multi-server setups; keep tool-enforced policy (Early Risers, dual order identifiers) as-is.

### Real storage & richer search

- Persist catalog, orders, and session history in a real DB (e.g. MySQL/Postgres) instead of JSON + in-process dicts.
- Keep a dedicated search index (OpenSearch/Elastic, or DB full-text) for lexical recall; add **embedding search** alongside it so paraphrases and fuzzy intent still hit the right SKUs.
- Hybrid retrieve (keyword + vectors) → rerank → return structured product cards the same way the demo UI does today.

---

## Prerequisites

- Python 3
- Node.js (`npm`)
- An OpenAI API key in `.env` at the repo root:

```env
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
NUDGE_IDLE_SECONDS=20
```

`.env` is gitignored. `./start.sh` creates `.venv` and installs frontend deps on first run.

`NUDGE_IDLE_SECONDS=20` is recommended for demos (default is `300` if unset).

## Commands

### 1. Start (API + UI)

```bash
./start.sh
```

- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:5173`

### 2. Unit tests

```bash
.venv/bin/pytest tests/
```

### 3. Evals

```bash
.venv/bin/python -m evals.eval_runner
```

---

## Product demo walkthrough

Open `http://127.0.0.1:5173`. Use **Reset** between scenarios so sessions stay clean.

### 1. Order tracking (valid)

```
What's the status of order #W001 for john.doe@example.com?
```

Expect: delivered status, products, and a USPS tracking link.

### 2. Invalid order tracking

```
What's the status of order #W001 for jane.smith@example.com?
```

Expect: no match (wrong email for that order). No invented tracking number.

Multi-turn variant:

1. `Track order #W001`
2. Agent asks for email → reply with an invalid / mismatched email

### 3. Product recommendations (text)

```
Recommend something for food or snacks on the trail
```

Expect: catalog hits such as energy drink / protein bars, with product cards.

### 4. Product recommendations (image)

Attach a product-like photo (e.g. cloak / outdoor gear) and ask:

```
Do you sell this?
```

Expect: agent looks at the image, searches the catalog, and returns a match when one exists (e.g. Nishita's Invisibility Cloak).

### 5. Honest miss (we don't carry it)

```
Do you have hiking boots?
```

or

```
Do you sell jackets?
```

Expect: clear “we don’t carry that” — no fake substitutes.

### 6. Early Risers promo (ineligible)

Outside 8:00–10:00 AM Pacific (or any time if you want the refusal path):

```
I'd like the Early Risers Promotion please
```

Expect: no code; agent explains the Pacific window. Generic “any coupons?” also must not mint a code.

*(To show a successful code, ask for Early Risers by name between 8:00–10:00 AM PT.)*

### 7. One-time idle nudge

1. Complete any short exchange (e.g. a catalog question).
2. Wait ~20 seconds (with `NUDGE_IDLE_SECONDS=20`).
3. Expect one check-in message + optional rating chip. It will not nudge again until **Reset**.

### 8. Human handoff

```
I want to talk to a human. I need a refund for a damaged shipment.
```

Expect: handoff queued banner. Agent does **not** mute — you can still ask about gear / orders / Early Risers while waiting.

### 9. Context / memory (multi-turn)

Same session keeps chat history until **Reset**. Do **not** Reset between steps.

**A. Slot-filling (order lookup across turns)**

1. `Track order #W001`
2. Expect: agent asks for the email (does not invent one).
3. `john.doe@example.com`
4. Expect: successful lookup using **both** turns — status + USPS link.

**B. Referring back to a prior recommendation**

1. `Recommend something for food or snacks on the trail`
2. Note a product it suggests (e.g. energy drink).
3. `Tell me more about the first one — what's the SKU and is it in stock?`
4. Expect: answers about that earlier product without you repeating the name.

**C. Topic switch, then recall**

1. Ask for a catalog recommendation (as in B).
2. `What's the status of order #W002 for jane.smith@example.com?`
3. `Actually, go back — do you still have that snack item you mentioned?`
4. Expect: remembers the earlier catalog suggestion after the order digression.

**D. Reset clears memory**

1. Complete any short exchange, then click **Reset**.
2. `What did I just ask you about?`
3. Expect: no carry-over from the old session.

## Developer controls (UI)

| Control | What it does |
|---|---|
| **Reset** | Clears the conversation and starts a fresh session (for retesting flows). |
| **Debug on** | Shows per-turn tool calls, model, tokens, and estimated cost. |

---

## Repository structure

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
