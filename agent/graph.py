from __future__ import annotations

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from agent.models import AgentState, ReconciliationResult, Discrepancy
from agent.tools import lookup_merchant_alias
from agent.loaders import get_loader


# ── LLM ────────────────────────────────────────────────────────────────────────

def get_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model="claude-haiku-4-5-20251001",
        api_key=os.environ["ANTHROPIC_API_KEY"],
    )


# ── Refined system prompt (Phase 5) ────────────────────────────────────────────

RECONCILE_SYSTEM_PROMPT = """You are a financial reconciliation assistant.

You will receive two lists of transactions — one from a bank ledger and one from Stripe.
Your job is to match them and identify discrepancies.

## Matching rules
- Match transactions by amount, date (±1 day for timezone drift), and description.
- Merchant names: descriptions may differ but refer to the same vendor (e.g. "AMZN MKTP US"
  vs "Amazon.com"). Use the lookup_merchant_alias tool on BOTH descriptions before concluding
  they differ. If they resolve to the same canonical name, treat them as matched.
- Refund netting: if a charge and its refund (negative amount) are BOTH present on BOTH sides
  and sum to zero, they are reconciled — do NOT flag them as a discrepancy.

## When to flag
Flag a discrepancy for any of these:
  - Amount differs by any amount (even $0.01)
  - Transaction exists on one side only, with no plausible match on the other
  - Date differs by more than 1 day
  - Currency mismatch

## Confidence and escalation rules
- confidence "high"   — mismatch is unambiguous (wrong amount, clearly missing transaction)
- confidence "medium" — descriptions differ but could be same vendor; date at the 1-day boundary
- confidence "low"    — genuinely uncertain whether two transactions are the same or different

CRITICAL RULE: if confidence is "low" for ANY reason, suggested_action MUST be
"escalate_to_human". Never auto-resolve a low-confidence case. When in doubt, escalate.

## Output
- Only include actual discrepancies — do not list matched transactions.
- Return an empty list if everything reconciles cleanly.
- Use bank_txn_id="NONE" when a transaction has no bank counterpart, and stripe_txn_id="NONE"
  when it has no Stripe counterpart."""


def _fmt(bank, stripe) -> str:
    b = "\n".join(
        f"  {t.id}  {t.date}  ${t.amount:.2f}  {t.currency}  {t.description}"
        for t in bank
    )
    s = "\n".join(
        f"  {t.id}  {t.date}  ${t.amount:.2f}  {t.currency}  fee=${t.fee:.2f}  {t.description}"
        for t in stripe
    )
    return f"BANK TRANSACTIONS:\n{b}\n\nSTRIPE TRANSACTIONS:\n{s}"


# ── Nodes ───────────────────────────────────────────────────────────────────────

def fetch_data_node(state: AgentState) -> AgentState:
    """Loads from the default loader (fixture / csv env var). Used by CLI and API."""
    loader = get_loader()
    bank   = loader.fetch_bank()
    stripe = loader.fetch_stripe()
    print(f"[fetch_data_node] bank={len(bank)} stripe={len(stripe)}")
    return {**state, "bank_transactions": bank, "stripe_transactions": stripe}


def _make_preloaded_fetch_node(bank: list, stripe: list):
    """Returns a fetch node with data baked in via closure. Used by Streamlit UI."""
    def preloaded_fetch_node(state: AgentState) -> AgentState:
        return {**state, "bank_transactions": bank, "stripe_transactions": stripe}
    return preloaded_fetch_node


def reconcile_node(state: AgentState) -> AgentState:
    print(f"[reconcile_node] bank={len(state['bank_transactions'])} stripe={len(state['stripe_transactions'])}")
    llm = (
        get_llm()
        .bind_tools([lookup_merchant_alias])
        .with_structured_output(ReconciliationResult)
    )
    messages = [
        SystemMessage(content=RECONCILE_SYSTEM_PROMPT),
        HumanMessage(content=_fmt(state["bank_transactions"], state["stripe_transactions"])),
    ]
    result: ReconciliationResult = llm.invoke(messages)
    print(f"[reconcile_node] found {len(result.discrepancies)} discrepancy(ies)")
    return {
        **state,
        "discrepancies": result.discrepancies,
        "status": "discrepancies_found" if result.discrepancies else "clean",
    }


def human_review_node(state: AgentState) -> AgentState:
    _log(f"\n[human_review_node] Processing human decisions...")
    decisions = state.get("human_decisions", {})
    approved, rejected, escalated = [], [], []

    for i, d in enumerate(state["discrepancies"]):
        decision = decisions.get(i, decisions.get(str(i), "no_decision"))
        _log(f"  [{i}] {d.reason[:65]}  => {decision.upper()}")
        if decision == "approve":
            approved.append(i)
        elif decision == "reject":
            rejected.append(i)
        else:
            escalated.append(i)

    _log(f"\n  Approved: {len(approved)}  Rejected: {len(rejected)}  Escalated: {len(escalated)}")
    return {
        **state,
        "status": "complete_with_escalations" if escalated else "complete_all_resolved",
    }


# ── Conditional edge ────────────────────────────────────────────────────────────

def route_after_reconcile(state: AgentState) -> str:
    return "human_review_node" if state["discrepancies"] else END


# ── Graph factory ───────────────────────────────────────────────────────────────

def build_graph(checkpointer=None, bank=None, stripe=None):
    """
    Build the agent graph.
    Pass bank + stripe to bake preloaded data into the fetch node (used by Streamlit UI).
    Omit both to use the default loader from DATA_SOURCE env var (CLI / API).
    """
    graph = StateGraph(AgentState)

    if bank and stripe:
        fetch_node = _make_preloaded_fetch_node(bank, stripe)
    else:
        fetch_node = fetch_data_node

    graph.add_node("fetch_data_node", fetch_node)
    graph.add_node("reconcile_node", reconcile_node)
    graph.add_node("human_review_node", human_review_node)

    graph.add_edge(START, "fetch_data_node")
    graph.add_edge("fetch_data_node", "reconcile_node")
    graph.add_conditional_edges("reconcile_node", route_after_reconcile)
    graph.add_edge("human_review_node", END)

    cp = checkpointer if checkpointer is not None else MemorySaver()
    return graph.compile(checkpointer=cp, interrupt_before=["human_review_node"])


EMPTY_STATE: AgentState = {
    "bank_transactions": [],
    "stripe_transactions": [],
    "discrepancies": [],
    "human_decisions": {},
    "status": "initialized",
}
