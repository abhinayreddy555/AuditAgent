# Reconciliation Agent — Build Plan

## Legend
- `[x]` Done
- `[~]` In progress
- `[ ]` Not started yet
- *(Stretch)* — optional, tackle after the phase is working

---

## Phase 1 — Foundation  ✅ COMPLETE

- [x] Create venv and install `langgraph`, `langchain-anthropic`, `pydantic`, `python-dotenv`
- [x] Define `BankTransaction`, `StripeTransaction`, `Discrepancy` Pydantic models
- [x] Define `AgentState` TypedDict
- [x] Build one-node `StateGraph` (`log_input → END`)
- [x] Confirm graph compiles and `invoke()` prints transactions

---

## Phase 2 — Graph Architecture  ✅ COMPLETE

- [x] Add `ANTHROPIC_API_KEY` to `.env`
- [x] Define `ReconciliationResult` Pydantic model (wraps `list[Discrepancy]`)
- [x] Implement `reconcile_node` using `with_structured_output(ReconciliationResult)`
- [x] Write reconcile system prompt (match by amount / date / description, flag mismatches)
- [x] Implement `human_review_node` stub (logs discrepancies, sets `status = "awaiting_human"`)
- [x] Write `route_after_reconcile` conditional edge function
- [x] Wire graph: `START → reconcile_node → (conditional) → human_review_node / END`
- [x] Test scenario A: matching transactions → graph ends without entering review node
- [x] Test scenario B: $0.50 amount mismatch → graph routes to `human_review_node`

---

## Phase 3 — Data Sources & Messy Fixtures  ✅ COMPLETE

- [x] Implement `fetch_bank_data()` returning 8–10 `BankTransaction` objects
- [x] Implement `fetch_stripe_data()` with intentional discrepancies woven in:
  - [x] Off-by-cent amount ($0.01–$0.03 rounding difference)
  - [x] Transaction present in bank but **missing** from Stripe
  - [x] Transaction present in Stripe but **missing** from bank
  - [x] Duplicate charge on one side only
  - [x] Refund (negative amount) that nets against an earlier charge
  - [x] Date shifted by 1 day (timezone drift)
  - [x] Same vendor, different merchant name (`"AMZN MKTP US"` vs `"Amazon.com"`)
- [x] Implement `fetch_data_node` (calls both functions, populates state)
- [x] Wire as new first node: `START → fetch_data_node → reconcile_node → ...`
- [x] Run full graph end-to-end with messy data, observe discrepancies found
- [x] *(Stretch)* Implement `@tool lookup_merchant_alias(name: str) -> str`
- [x] *(Stretch)* Bind merchant alias tool to `reconcile_node`'s LLM

---

## Phase 4 — Human-in-the-Loop & Persistence  ✅ COMPLETE

- [x] Add `MemorySaver()` checkpointer to `graph.compile()`
- [x] Add `interrupt_before=["human_review_node"]` to `compile()`
- [x] Run graph with `config = {"configurable": {"thread_id": "run-001"}}`
- [x] Verify execution **pauses** before `human_review_node`
- [x] Inspect paused state with `graph.get_state(config)` — confirm discrepancies visible
- [x] Update `human_review_node` to read `state.human_decisions` and produce final summary
- [x] Resume: `graph.update_state(config, {"human_decisions": {...}})`
- [x] Resume: `graph.invoke(None, config)` → confirm graph completes
- [x] Write `__main__` demo showing full **pause → inspect → decide → resume → summary** flow

---

## Phase 5 — Observability & Refinement  ✅ COMPLETE

- [x] Add `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` to `.env` (ready to enable)
- [x] Tracing indicator in `main.py` — shows ON/OFF at startup
- [x] Audit reconcile prompt for **refund-netting** — explicit rule added, verified working
- [x] Audit reconcile prompt for **merchant-alias** — tool + rule added, verified working
- [x] Add rule: `confidence == "low"` => `suggested_action` must be `"escalate_to_human"`
- [x] Add stress-test pair (Adobe SYSTEMS vs Adobe Creative Cloud) — resolved correctly via alias tool
- [x] Stress-test check in `main.py` — prints PASS/FAIL for escalation rule
- [x] Refactored into `agent/` package: `models.py`, `data.py`, `tools.py`, `graph.py`
- [x] *(Stretch)* FastAPI app: `POST /run` and `POST /resume` in `agent/api.py`

---

## Stretch Goals

- [x] `lookup_merchant_alias` `@tool` (Phase 3 + wired in Phase 5 package)
- [x] FastAPI wrapper: `POST /run` + `POST /resume` (Phase 5)
- [ ] Save `langgraph-builder` skill to `~/.claude/skills/langgraph-builder/SKILL.md`
