"""
Streamlit UI for the Reconciliation Agent.
Run with: streamlit run app.py
"""
import sys
import tempfile
import pathlib
import uuid
import importlib
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# Force-reload agent.graph on every Streamlit rerun so code changes are always picked up
import agent.graph as _graph_module
importlib.reload(_graph_module)
from agent.graph import build_graph, EMPTY_STATE
from agent.models import Discrepancy

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="AuditAgent",
    page_icon="🏦",
    layout="wide",
)

# ── Session state defaults ─────────────────────────────────────────────────────

if "stage"         not in st.session_state: st.session_state.stage         = "idle"
if "graph"         not in st.session_state: st.session_state.graph         = build_graph()
if "thread_id"     not in st.session_state: st.session_state.thread_id     = None
if "discrepancies" not in st.session_state: st.session_state.discrepancies = []
if "final"         not in st.session_state: st.session_state.final         = None
if "bank_txns"     not in st.session_state: st.session_state.bank_txns     = None
if "stripe_txns"   not in st.session_state: st.session_state.stripe_txns   = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def confidence_color(c: str) -> str:
    return {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(c, "⚪")


def _save_upload(uploaded_file, filename: str) -> str:
    tmp = pathlib.Path(tempfile.gettempdir()) / filename
    tmp.write_bytes(uploaded_file.getvalue())
    return str(tmp)


def run_agent():
    """Build a fresh graph with uploaded data baked in, then invoke until interrupt."""
    bank_txns   = st.session_state.bank_txns   or []
    stripe_txns = st.session_state.stripe_txns or []

    # Bake data into the graph via closure — avoids LangGraph serialization issues
    graph = build_graph(bank=bank_txns, stripe=stripe_txns)
    st.session_state.graph = graph

    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}
    graph.invoke(EMPTY_STATE, config)

    snapshot = graph.get_state(config)
    st.session_state.thread_id     = thread_id
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
    st.session_state.stage         = "idle"
    st.session_state.thread_id     = None
    st.session_state.discrepancies = []
    st.session_state.final         = None
    st.session_state.bank_txns     = None
    st.session_state.stripe_txns   = None
    st.session_state.graph         = build_graph()


CSV_FORMAT_HELP = """
**Expected CSV format**

| File | Required columns | Optional |
|---|---|---|
| Bank export | `id`, `date`, `amount`, `description` | `currency` (default USD) |
| Stripe export | `id`, `date`, `amount`, `description`, `fee` | `currency` (default USD) |

- `date` — ISO format preferred: `YYYY-MM-DD`. Also accepts `MM/DD/YYYY` and `DD/MM/YYYY`
- `amount` — decimal number. Negative for refunds / credits (e.g. `-29.99`)
- `fee` — Stripe processing fee (set 0 if not available)

*bank_export.csv*
```
id,date,amount,description,currency
TXN001,2024-06-01,500.00,Payroll deposit,USD
```

*stripe_export.csv*
```
id,date,amount,description,currency,fee
ch_001,2024-06-01,500.00,Payroll deposit,USD,0.00
```
"""


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
1. **Fetches** bank and Stripe transactions from a data source you choose
2. **Sends** both lists to Claude in a single API call for fuzzy comparison
3. **Returns** a structured list of discrepancies — amounts, missing transactions, date drift, duplicates
4. **Pauses** and asks *you* to review each one
5. **Resumes** with your decisions and produces a final report
        """)
    with col2:
        st.subheader("Data source")
        st.metric("Sample bank txns", 200)
        st.metric("Sample Stripe txns", "~197")
        st.metric("Discrepancy types", "6+")

    st.divider()

    # ── Data source selector ───────────────────────────────────────────────────
    st.subheader("Choose your data source")
    source = st.radio(
        "Data source",
        options=["sample", "bank_only", "both"],
        format_func=lambda x: {
            "sample":    "📦  Built-in sample data  (200 synthetic transactions, no upload needed)",
            "bank_only": "🏦  Upload bank CSV only  (Stripe side auto-generated — works with Kaggle data)",
            "both":      "📂  Upload bank + Stripe CSVs  (you have both exports)",
        }[x],
        label_visibility="collapsed",
    )

    ready = False

    # ── Sample data ────────────────────────────────────────────────────────────
    if source == "sample":
        st.info(
            "Uses the 200-row synthetic dataset in `data/sample/`. "
            "Run `python scripts/generate_test_data.py --sample` to regenerate with new noise.",
            icon="ℹ️",
        )
        from agent.loaders.csv_loader import CsvLoader
        try:
            loader = CsvLoader("data/sample/bank_export.csv", "data/sample/stripe_export.csv")
            st.session_state.bank_txns   = loader.fetch_bank()
            st.session_state.stripe_txns = loader.fetch_stripe()
            st.success(
                f"Loaded **{len(st.session_state.bank_txns)} bank** and "
                f"**{len(st.session_state.stripe_txns)} Stripe** transactions.",
                icon="✅",
            )
            ready = True
        except FileNotFoundError:
            st.error("Sample data not found. Run: `python scripts/generate_test_data.py --sample`")

    # ── Bank CSV only ──────────────────────────────────────────────────────────
    elif source == "bank_only":
        st.info(
            "Upload any bank transaction CSV — your own export or the "
            "[Kaggle fraud detection dataset](https://www.kaggle.com/datasets/kartik2112/fraud-detection). "
            "The Stripe side is derived automatically with realistic noise injected.",
            icon="ℹ️",
        )

        with st.expander("📋  What columns does my CSV need?", expanded=False):
            st.markdown("""
**Column names are detected automatically.** These are recognised:

| Role | Accepted column names |
|---|---|
| ID | `id`, `trans_num`, `transaction_id`, `txn_id` |
| Date | `date`, `trans_date_trans_time`, `transaction_date`, `datetime` |
| Amount | `amount`, `amt`, `transaction_amount`, `debit` |
| Description | `description`, `merchant`, `merchant_name`, `name`, `payee`, `category` |
| Currency | `currency` (optional — defaults to USD) |

Works out of the box with the **Kaggle fraud detection CSV** (`fraudTrain.csv` / `fraudTest.csv`).
            """)

        bank_file = st.file_uploader(
            "Bank CSV",
            type=["csv"],
            key="bank_only_upload",
            help="Your bank export, Kaggle fraudTrain.csv, or any transaction CSV",
        )
        max_rows = st.slider(
            "Max rows to process",
            min_value=50, max_value=500, value=200, step=50,
            help="Claude reads all rows in one call. 200 is a good starting point.",
        )

        if bank_file:
            try:
                bank_path = _save_upload(bank_file, "audit_bank_only.csv")
                from agent.loaders.bank_only_loader import BankOnlyLoader
                loader = BankOnlyLoader(bank_path, max_rows=max_rows)
                st.session_state.bank_txns   = loader.fetch_bank()
                st.session_state.stripe_txns = loader.fetch_stripe()
                st.success(
                    f"**{bank_file.name}** — "
                    f"**{len(st.session_state.bank_txns)} bank** transactions loaded. "
                    f"Stripe side auto-generated: **{len(st.session_state.stripe_txns)} rows**.",
                    icon="✅",
                )
                ready = True
            except Exception as e:
                st.error(f"Could not parse CSV: {e}")
        else:
            st.warning("Upload a bank CSV to continue.", icon="⚠️")

    # ── Both CSVs ──────────────────────────────────────────────────────────────
    else:
        with st.expander("📋  Expected CSV format — click to expand", expanded=False):
            st.markdown(CSV_FORMAT_HELP)

        col_b, col_s = st.columns(2)
        with col_b:
            bank_file = st.file_uploader(
                "Bank export CSV", type=["csv"], key="bank_upload",
                help="Download from your bank's online portal",
            )
        with col_s:
            stripe_file = st.file_uploader(
                "Stripe export CSV", type=["csv"], key="stripe_upload",
                help="Stripe Dashboard -> Reports -> Balance -> Download",
            )

        if bank_file and stripe_file:
            try:
                bank_path   = _save_upload(bank_file,   "audit_bank_upload.csv")
                stripe_path = _save_upload(stripe_file, "audit_stripe_upload.csv")
                from agent.loaders.csv_loader import CsvLoader
                loader = CsvLoader(bank_path, stripe_path)
                st.session_state.bank_txns   = loader.fetch_bank()
                st.session_state.stripe_txns = loader.fetch_stripe()
                st.success(
                    f"Bank: **{bank_file.name}** ({len(st.session_state.bank_txns)} rows)  |  "
                    f"Stripe: **{stripe_file.name}** ({len(st.session_state.stripe_txns)} rows)",
                    icon="✅",
                )
                ready = True
            except Exception as e:
                st.error(f"Could not parse CSV: {e}")
        else:
            st.warning("Upload both files to continue.", icon="⚠️")

    st.divider()
    if st.button("▶  Run Reconciliation", type="primary", use_container_width=True, disabled=not ready):
        with st.spinner("Sending to Claude for comparison…"):
            run_agent()
        st.rerun()

# ── STAGE: clean ──────────────────────────────────────────────────────────────

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
    final         = st.session_state.final
    discrepancies = final.get("discrepancies", [])
    decisions     = final.get("human_decisions", {})

    approved  = sum(1 for v in decisions.values() if v == "approve")
    rejected  = sum(1 for v in decisions.values() if v == "reject")
    escalated = sum(1 for v in decisions.values() if v == "escalate")

    if escalated:
        st.warning(f"### ⚠️  Run complete — {escalated} case(s) escalated for senior review")
    else:
        st.success("### ✅  Run complete — all issues resolved")

    st.divider()
    cols = st.columns(6)
    cols[0].metric("Bank transactions",   len(final.get("bank_transactions", [])))
    cols[1].metric("Stripe transactions", len(final.get("stripe_transactions", [])))
    cols[2].metric("Discrepancies",       len(discrepancies))
    cols[3].metric("✅ Approved",          approved)
    cols[4].metric("❌ Rejected",          rejected)
    cols[5].metric("⚠️ Escalated",         escalated)

    st.divider()
    st.subheader("Decision summary")

    decision_labels   = {"approve": "✅ Approved", "reject": "❌ Rejected", "escalate": "⚠️ Escalated"}
    confidence_labels = {"high": "🔴 High", "medium": "🟡 Medium", "low": "⚪ Low"}

    table_data = []
    for i, d in enumerate(discrepancies):
        dec = decisions.get(i, decisions.get(str(i), "—"))
        table_data.append({
            "#":          i,
            "Bank ID":    d.bank_txn_id,
            "Stripe ID":  d.stripe_txn_id,
            "Confidence": confidence_labels.get(d.confidence, d.confidence),
            "Reason":     d.reason,
            "Decision":   decision_labels.get(dec, dec),
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

    st.divider()
    if st.button("↺  Run a new reconciliation", use_container_width=True):
        reset()
        st.rerun()
