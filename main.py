"""
Phase 5: Observability, prompt stress-test, and structured demo.
Imports from the agent/ package. Run: .venv\\Scripts\\python.exe main.py
"""
from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

# ── Optional: enable LangSmith tracing ────────────────────────────────────────
# Uncomment these (or set them in .env) to see full traces in LangSmith:
#   LANGCHAIN_TRACING_V2=true
#   LANGCHAIN_API_KEY=your_langsmith_key_here
if os.getenv("LANGCHAIN_TRACING_V2") == "true":
    print("[tracing] LangSmith tracing is ON")
else:
    print("[tracing] LangSmith tracing is OFF  (set LANGCHAIN_TRACING_V2=true in .env to enable)")

from agent.graph import build_graph, EMPTY_STATE
from agent.models import Discrepancy
from agent.report import generate_report


def separator(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


if __name__ == "__main__":
    app = build_graph()
    config = {"configurable": {"thread_id": "phase5-demo"}}

    # ── STEP 1: run until interrupt ────────────────────────────────────────────
    separator("STEP 1  Starting graph")
    app.invoke(EMPTY_STATE, config)

    # ── STEP 2: inspect frozen state ──────────────────────────────────────────
    separator("STEP 2  Inspecting paused state")
    snapshot = app.get_state(config)
    discrepancies: list[Discrepancy] = snapshot.values["discrepancies"]

    print(f"Next node      : {snapshot.next}")
    print(f"Discrepancies  : {len(discrepancies)}\n")

    for i, d in enumerate(discrepancies):
        tag = ""
        if d.confidence == "low":
            tag = "  <<< LOW CONFIDENCE — must escalate"
        print(f"  [{i}] confidence={d.confidence}{tag}")
        print(f"       bank={d.bank_txn_id}  stripe={d.stripe_txn_id}")
        print(f"       reason   : {d.reason}")
        print(f"       suggested: {d.suggested_action}\n")

    # ── STEP 3: stress-test check ──────────────────────────────────────────────
    separator("STEP 3  Stress-test: verifying low-confidence escalation rule")
    low_conf = [d for d in discrepancies if d.confidence == "low"]
    wrong    = [d for d in low_conf if d.suggested_action != "escalate_to_human"]

    if low_conf:
        print(f"Low-confidence discrepancies found : {len(low_conf)}")
        for d in low_conf:
            print(f"  bank={d.bank_txn_id}  stripe={d.stripe_txn_id}")
            print(f"  suggested_action = {d.suggested_action}")
        if wrong:
            print(f"\n  RULE VIOLATION: {len(wrong)} low-confidence case(s) not escalated!")
        else:
            print("\n  PASS: all low-confidence cases correctly set to escalate_to_human")
    else:
        print("No low-confidence discrepancies in this run.")
        print("(The Adobe SYSTEMS / Adobe Creative Cloud pair may have been resolved via alias tool)")

    # ── STEP 4: simulate human decisions ──────────────────────────────────────
    separator("STEP 4  Human reviews and enters decisions")
    human_decisions: dict[int, str] = {}
    for i, d in enumerate(discrepancies):
        if d.confidence == "low":
            human_decisions[i] = "escalate"   # rule: always escalate low confidence
        elif d.confidence == "medium":
            human_decisions[i] = "approve"    # timezone drift — expected
        else:
            # High confidence — decide based on type
            if "duplicate" in d.reason.lower():
                human_decisions[i] = "reject"
            elif "missing" in d.reason.lower() or "no matching" in d.reason.lower() or "no corresponding" in d.reason.lower():
                human_decisions[i] = "escalate"
            else:
                human_decisions[i] = "reject"

    for i, decision in human_decisions.items():
        d = discrepancies[i]
        print(f"  [{i}] {d.confidence:6s}  => {decision.upper()}")

    # ── STEP 5: resume ────────────────────────────────────────────────────────
    separator("STEP 5  Resuming graph with decisions")
    app.update_state(config, {"human_decisions": human_decisions})
    final = app.invoke(None, config)

    # ── STEP 6: generate HTML report ──────────────────────────────────────────
    separator("STEP 6  Generating HTML report")
    report_path = generate_report(final, output_path="report.html", auto_open=True)
    print(f"Report written : {report_path}")
    print("Opening in browser...")

    print("\n-- To enable LangSmith tracing, add to .env:")
    print("   LANGCHAIN_TRACING_V2=true")
    print("   LANGCHAIN_API_KEY=<your key from smith.langchain.com>")
    print("\n-- To start the FastAPI server:")
    print("   .venv\\Scripts\\uvicorn.exe agent.api:app --reload")
    print("   Then open http://127.0.0.1:8000/docs for the interactive API")
