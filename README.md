# AuditAgent

Autonomous transaction reconciliation agent built with LangGraph and Claude. Compares bank and Stripe records, flags discrepancies using AI judgment, and pauses for human review before completing — all in a resumable state machine.

Works with your own data: upload any bank CSV export (including the Kaggle fraud detection dataset) and the agent generates the Stripe side automatically with realistic noise — or bring both files if you have them. A 200-row synthetic dataset is included so it runs out of the box with no upload needed.

---

## What it does

1. **Fetches** bank and Stripe transaction records — from uploaded CSVs, the built-in sample dataset, or any custom loader
2. **Sends** both lists to Claude in a single API call for fuzzy comparison via `with_structured_output()` — returns typed `Discrepancy` objects, never free text
3. **Handles** messy real-world data automatically: rounding differences, duplicate charges, refund netting, timezone drift, merchant name variants
4. **Pauses** before human review using LangGraph's interrupt mechanism — state is checkpointed, the process does not block
5. **Resumes** exactly where it stopped after the human submits decisions
6. **Presents** a final report in an interactive Streamlit UI

---

## Quick start

```bash
# 1. Clone and enter the project
git clone https://github.com/abhinayreddy555/AuditAgent.git
cd AuditAgent

# 2. Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac / Linux

# 3. Install dependencies
pip install langgraph langchain-anthropic pydantic python-dotenv streamlit fastapi uvicorn

# 4. Add your Anthropic API key
# Create a .env file:
# ANTHROPIC_API_KEY=your_key_here

# 5. Launch the Streamlit UI
streamlit run app.py
```

Open **http://localhost:8501** and choose a data source on the home screen.

---

## Data sources

The agent supports three modes, controlled by `DATA_SOURCE` in your `.env`:

| Mode | How to activate | What it uses |
|---|---|---|
| **Sample data** (default) | Select in UI or set `DATA_SOURCE=csv` with sample paths | 200-row synthetic dataset in `data/sample/` — discrepancies pre-injected |
| **Upload your own CSVs** | Select "Upload your own CSVs" in the UI | Bank export + Stripe export from your own accounts |
| **Demo fixture** | `DATA_SOURCE=fixture` in `.env` | 10 hardcoded transactions — useful for unit testing |

### Bringing your own data

Export these files from your accounts and upload them in the Streamlit UI:

- **Bank CSV** — most online banking portals: Transactions → Export → CSV
- **Stripe CSV** — Stripe Dashboard → Reports → Balance → Download

Expected columns:

| File | Required | Optional |
|---|---|---|
| `bank_export.csv` | `id`, `date`, `amount`, `description` | `currency` (default USD) |
| `stripe_export.csv` | `id`, `date`, `amount`, `description`, `fee` | `currency` (default USD) |

Dates are accepted as `YYYY-MM-DD`, `MM/DD/YYYY`, or `DD/MM/YYYY`. Negative amounts represent refunds.

### Generating a larger test dataset

The included script generates realistic CSVs with injected discrepancies. No external account needed:

```bash
# Regenerate the 200-row sample
python scripts/generate_test_data.py --sample

# Generate a larger set (e.g. 500 rows)
python scripts/generate_test_data.py --rows 500 --out data

# Use the Kaggle fraud detection dataset as source
# Download fraudTrain.csv from https://www.kaggle.com/datasets/kartik2112/fraud-detection
python scripts/generate_test_data.py --kaggle scripts/fraudTrain.csv --rows 500
```

Discrepancy types the script injects into the Stripe side:

| Type | Rate |
|---|---|
| Amount rounding (± $0.01–$0.03) | 5% of rows |
| Missing from Stripe | 3% of rows |
| Date drift (± 1 day) | 4% of rows |
| Duplicate charge | 2% of rows |
| Merchant name variant | 5% of rows |
| Extra charge on Stripe only | 2% of rows |

---

## How Claude processes transactions

Claude receives **all rows in a single API call** — not one call per transaction. The prompt contains the full bank list and the full Stripe list. Claude reads both simultaneously, matches them, and returns only the mismatches as typed `Discrepancy` objects.

```
fetch_data_node → builds one prompt with ALL rows
                       ↓  1 API call
                    Claude reads both lists, matches by amount + date + description
                       ↓  1 response
                    list[Discrepancy] — only the mismatches
```

The only exception: `lookup_merchant_alias()` tool calls happen inline when Claude encounters ambiguous merchant names. These are part of the same logical call.

Practical limits: up to ~500 rows works well in one call. For larger datasets, chunk by date range and run one call per chunk.

---

## Running modes

| Mode | Command | What it does |
|---|---|---|
| Streamlit UI | `streamlit run app.py` | Interactive browser app — choose data source, run, review, resume |
| CLI demo | `python main.py` | Full pause → inspect → resume flow in the terminal (uses fixture data) |
| REST API | `uvicorn agent.api:app --reload` | `POST /run` and `POST /resume` endpoints |
| API docs | open `http://localhost:8000/docs` | Interactive Swagger UI for the REST API |

---

## Agent architecture

```mermaid
flowchart TD
    START([START]) --> FD

    FD["fetch_data_node — pulls bank + Stripe records"]
    FD --> RN

    RN["reconcile_node — Claude finds discrepancies"]
    RN --> CE

    CE{"Discrepancies found?"}
    CE -->|No|  END_CLEAN([END])
    CE -->|Yes| HR

    HR["human_review_node — graph pauses · human decides · graph resumes"]
    HR --> END_DONE([END])

    style FD        fill:#d4edda,stroke:#28a745,color:#000
    style RN        fill:#cce5ff,stroke:#004085,color:#000
    style CE        fill:#fff3cd,stroke:#856404,color:#000
    style HR        fill:#f8d7da,stroke:#721c24,color:#000
    style START     fill:#343a40,color:#fff,stroke:#343a40
    style END_CLEAN fill:#28a745,color:#fff,stroke:#28a745
    style END_DONE  fill:#28a745,color:#fff,stroke:#28a745
```

| Colour | Layer |
|---|---|
| Green | Plain Python |
| Blue | Claude AI — structured judgment |
| Yellow | LangGraph — conditional routing |
| Red | Human-in-the-loop — graph pauses and waits |

> LangSmith traces every Claude call automatically when `LANGCHAIN_TRACING_V2=true` is set — see [Enabling LangSmith tracing](#enabling-langsmith-tracing) below.

---

## Discrepancy types handled

| Type | Example | Handled by |
|---|---|---|
| Amount rounding | Bank $120.00 vs Stripe $120.02 | Claude flags, human decides |
| Missing transaction | Netflix on bank, absent from Stripe | Claude flags |
| Duplicate charge | Gym membership posted twice on bank | Claude flags |
| Refund netting | +$200 charge and -$200 refund, both sides | Claude resolves automatically |
| Timezone drift | Bank June 7, Stripe June 8 — same transaction | Claude flags at medium confidence |
| Merchant name variants | "AMZN MKTP US" vs "Amazon.com" | `lookup_merchant_alias` tool resolves |
| Missing from bank | Spotify on Stripe, absent from bank | Claude flags |

---

## Human-in-the-loop pattern

The core LangGraph pattern this project demonstrates:

```python
# Compile with checkpointer and interrupt point
app = graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["human_review_node"]
)

# Call 1 — runs fetch + reconcile, then pauses
app.invoke(initial_state, config)

# Inspect frozen state
snapshot = app.get_state(config)
discrepancies = snapshot.values["discrepancies"]

# Inject human decisions
app.update_state(config, {"human_decisions": {0: "reject", 1: "escalate"}})

# Call 2 — resumes from checkpoint, runs human_review_node, completes
app.invoke(None, config)
```

`invoke(None, config)` means "resume thread from last checkpoint" — the human could come back hours later and the graph picks up exactly where it stopped.

---

## Enabling LangSmith tracing

```bash
# Add to .env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key_here
```

Sign up free at [smith.langchain.com](https://smith.langchain.com). Every Claude call is logged with the exact prompt sent, response received, latency, and token count.

---

## Project structure

```
AuditAgent/
├── agent/
│   ├── models.py              ← Pydantic schemas: BankTransaction, Discrepancy, AgentState
│   ├── data.py                ← 10-row hardcoded fixture (demo / fallback)
│   ├── loaders/
│   │   ├── base.py            ← DataLoader protocol + get_loader() factory
│   │   ├── fixture.py         ← Wraps data.py — used when DATA_SOURCE=fixture
│   │   ├── csv_loader.py      ← Reads any bank + Stripe CSV pair
│   │   ├── bank_only_loader.py← Reads one bank CSV, derives Stripe side automatically
│   │   └── derive_stripe.py   ← Injects realistic noise into a bank transaction list
│   ├── tools.py               ← lookup_merchant_alias @tool
│   ├── graph.py               ← Nodes, edges, system prompt, build_graph()
│   └── api.py                 ← FastAPI: POST /run and POST /resume
├── data/
│   └── sample/
│       ├── bank_export.csv    ← 200-row synthetic dataset (committed)
│       └── stripe_export.csv  ← Derived with injected discrepancies (committed)
├── scripts/
│   └── generate_test_data.py  ← Generates CSVs from synthetic data or Kaggle dataset
├── app.py                     ← Streamlit UI: sample data / upload bank only / upload both
├── main.py                    ← CLI demo: full pause → inspect → decide → resume flow
├── PLAN.md                    ← Step-level build checklist (all complete)
└── .env                       ← API keys — never commit this
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` |
| LLM | [Claude](https://www.anthropic.com) via `langchain-anthropic` |
| Validation | Pydantic v2 |
| Persistence | `MemorySaver` (swap for PostgreSQL/Redis in production) |
| UI | Streamlit |
| API | FastAPI + Uvicorn |
| Observability | LangSmith (optional) |

---

## What to build next

This project demonstrates the core patterns that appear in every real-world agentic system. The same structure — fetch → AI judgment → conditional route → human gate → resume — applies directly to:

- **Invoice approval** — extract vendor + amount from email, route high-value invoices to a manager, resume after sign-off
- **Support triage** — classify incoming tickets, auto-reply to low-urgency, interrupt for high-urgency human response
- **Data quality** — scheduled agent that scans a database, flags anomalies, waits for acknowledgement before archiving
