"""
Streamlit UI for the Reconciliation Agent.
Run with: .venv\\Scripts\\streamlit.exe run app.py
"""
import uuid
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agent.graph import build_graph, EMPTY_STATE
from agent.models import Discrepancy

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AuditAgent",
    page_icon="🏦",
    layout="wide",
)

# ── Session state defaults ─────────────────────────────────────────────────────
# Streamlit reruns the whole script on every interaction.
# session_state is the only thing that survives between reruns.

if "stage" not in st.session_state:
    st.session_state.stage = "idle"          # idle | awaiting | complete
if "graph" not in st.session_state:
    st.session_state.graph = build_graph()
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "discrepancies" not in st.session_state:
    st.session_state.discrepancies = []
if "final" not in st.session_state:
    st.session_state.final = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def confidence_color(c: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(c, "⚪")


def run_agent():
    """Start a new reconciliation run. Runs until the interrupt."""
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    st.session_state.graph.invoke(EMPTY_STATE, config)
    snapshot = st.session_state.graph.get_state(config)
    st.session_state.thread_id = thread_id
    st.session_state.discrepancies = snapshot.values.get("discrepancies", [])
    st.session_state.stage = (
        "awaiting" if st.session_state.discrepancies else "complete_clean"
    )
    if st.session_state.stage == "complete_clean":
        st.session_state.final = snapshot.values


def submit_decisions(decisions: dict[int, str]):
    """Inject human decisions and resume the graph."""
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    st.session_state.graph.update_state(config, {"human_decisions": decisions})
    final = st.session_state.graph.invoke(None, config)
    st.session_state.final = final
    st.session_state.stage = "complete"


def reset():
    st.session_state.stage = "idle"
    st.session_state.thread_id = None
    st.session_state.discrepancies = []
    st.session_state.final = None
    st.session_state.graph = build_graph()   # fresh checkpointer


# ── Header ─────────────────────────────────────────────────────────────────────

st.title("🏦 AuditAgent")
st.caption("Autonomous Transaction Reconciliation · LangGraph + Claude · Human-in-the-Loop")
st.divider()

# ── STAGE: idle ────────────────────────────────────────────────────────────────

if st.session_state.stage == "idle":
    col1, col2 = st.columns([2, 1])
    with col1:
        st.subheader("What this agent does")
        st.markdown("""
1. **Fetches** bank and Stripe transactions from simulated data sources
2. **Sends** both lists to Claude for fuzzy comparison
3. **Returns** a structured list of discrepancies — amounts, missing transactions, date drift, duplicates
4. **Pauses** and asks *you* to review each one
5. **Resumes** with your decisions and produces a final report
        """)
    with col2:
        st.subheader("Data loaded")
        st.metric("Bank transactions", 10)
        st.metric("Stripe transactions", 9)
        st.metric("Intentional discrepancy types", 7)

    st.divider()
    if st.button("▶  Run Reconciliation", type="primary", use_container_width=True):
        with st.spinner("Fetching transactions and running Claude comparison…"):
            run_agent()
        st.rerun()

# ── STAGE: clean (no discrepancies) ───────────────────────────────────────────

elif st.session_state.stage == "complete_clean":
    st.success("### ✅ All transactions reconciled cleanly")
    st.write("Claude found no discrepancies. No human review needed.")
    if st.button("Run again", use_container_width=True):
        reset()
        st.rerun()

# ── STAGE: awaiting human decisions ───────────────────────────────────────────

elif st.session_state.stage == "awaiting":
    discrepancies: list[Discrepancy] = st.session_state.discrepancies

    st.subheader(f"⏸  Graph paused — {len(discrepancies)} discrepancy(ies) need your review")
    st.info(
        "The agent has stopped and is waiting for you. "
        "Review each issue below, choose a decision, then click **Submit decisions** to resume.",
        icon="ℹ️",
    )

    decisions: dict[int, str] = {}

    for i, d in enumerate(discrepancies):
        icon = confidence_color(d.confidence)
        with st.expander(f"{icon} [{i}]  {d.reason[:90]}{'…' if len(d.reason) > 90 else ''}", expanded=True):
            col_left, col_right = st.columns([3, 1])
            with col_left:
                st.markdown(f"**Reason:** {d.reason}")
                st.markdown(f"**Suggested action:** `{d.suggested_action.replace('_', ' ')}`")
                cols = st.columns(3)
                cols[0].metric("Bank ID", d.bank_txn_id)
                cols[1].metric("Stripe ID", d.stripe_txn_id)
                cols[2].metric("Confidence", d.confidence.upper())
            with col_right:
                decision = st.radio(
                    "Your decision",
                    options=["approve", "reject", "escalate"],
                    index=1 if d.confidence == "high" else 0,
                    key=f"decision_{i}",
                    format_func=lambda x: {
                        "approve":  "✅ Approve",
                        "reject":   "❌ Reject",
                        "escalate": "⚠️ Escalate",
                    }[x],
                )
                decisions[i] = decision

    st.divider()
    col_submit, col_reset = st.columns([3, 1])
    with col_submit:
        if st.button("✔  Submit decisions & resume agent", type="primary", use_container_width=True):
            with st.spinner("Resuming graph with your decisions…"):
                submit_decisions(decisions)
            st.rerun()
    with col_reset:
        if st.button("↺  Start over", use_container_width=True):
            reset()
            st.rerun()

# ── STAGE: complete ────────────────────────────────────────────────────────────

elif st.session_state.stage == "complete":
    final = st.session_state.final
    discrepancies: list[Discrepancy] = final.get("discrepancies", [])
    decisions: dict = final.get("human_decisions", {})
    status = final.get("status", "unknown")

    approved  = sum(1 for v in decisions.values() if v == "approve")
    rejected  = sum(1 for v in decisions.values() if v == "reject")
    escalated = sum(1 for v in decisions.values() if v == "escalate")

    if escalated:
        st.warning(f"### ⚠️  Run complete — {escalated} case(s) escalated for senior review")
    else:
        st.success("### ✅  Run complete — all issues resolved")

    # ── Summary metrics ────────────────────────────────────────────────────────
    st.divider()
    cols = st.columns(6)
    cols[0].metric("Bank transactions", len(final.get("bank_transactions", [])))
    cols[1].metric("Stripe transactions", len(final.get("stripe_transactions", [])))
    cols[2].metric("Discrepancies", len(discrepancies))
    cols[3].metric("✅ Approved", approved)
    cols[4].metric("❌ Rejected", rejected)
    cols[5].metric("⚠️ Escalated", escalated)

    # ── Decision table ─────────────────────────────────────────────────────────
    st.divider()
    st.subheader("Decision summary")

    decision_labels = {"approve": "✅ Approved", "reject": "❌ Rejected", "escalate": "⚠️ Escalated"}
    confidence_labels = {"high": "🔴 High", "medium": "🟡 Medium", "low": "⚪ Low"}

    table_data = []
    for i, d in enumerate(discrepancies):
        dec = decisions.get(i, decisions.get(str(i), "—"))
        table_data.append({
            "#": i,
            "Bank ID": d.bank_txn_id,
            "Stripe ID": d.stripe_txn_id,
            "Confidence": confidence_labels.get(d.confidence, d.confidence),
            "Reason": d.reason,
            "Decision": decision_labels.get(dec, dec),
        })

    if table_data:
        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "#":          st.column_config.NumberColumn(width="small"),
                "Bank ID":    st.column_config.TextColumn(width="small"),
                "Stripe ID":  st.column_config.TextColumn(width="small"),
                "Confidence": st.column_config.TextColumn(width="small"),
                "Reason":     st.column_config.TextColumn(width="large"),
                "Decision":   st.column_config.TextColumn(width="medium"),
            },
        )

    # ── What the agent did automatically ──────────────────────────────────────
    st.divider()
    st.subheader("What the agent handled automatically (no human needed)")
    st.markdown("""
- **Refund pair** — Airline ticket charge (+$200) and refund (-$200) both present on both sides. Net = $0. Not flagged. ✅
- **Merchant name variants** — "STARBUCKS STORE #4021" (bank) matched to "Starbucks" (Stripe) via the `lookup_merchant_alias` tool. Not flagged. ✅
- **Adobe stress test** — "ADOBE SYSTEMS" (bank) matched to "Adobe Creative Cloud" (Stripe). Same vendor resolved by tool. Not flagged. ✅
- **Payroll deposit** — Exact match on both sides. Passed through silently. ✅
    """)

    st.divider()
    if st.button("↺  Run a new reconciliation", use_container_width=True):
        reset()
        st.rerun()
