"""
FastAPI wrapper — Phase 5 stretch goal.

POST /run    — start a reconciliation run, returns thread_id + pending discrepancies
POST /resume — supply human decisions for a paused run, returns final summary

Run with:
    .venv\\Scripts\\uvicorn.exe agent.api:app --reload
"""
from __future__ import annotations

import uuid
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent.graph import build_graph, EMPTY_STATE
from agent.models import Discrepancy

load_dotenv()

app = FastAPI(title="Reconciliation Agent", version="1.0")

# One shared graph instance — MemorySaver lives in memory per process
_graph = build_graph()


# ── Request / response schemas ─────────────────────────────────────────────────

class RunResponse(BaseModel):
    thread_id: str
    status: str
    discrepancy_count: int
    discrepancies: list[Discrepancy]
    message: str


class ResumeRequest(BaseModel):
    thread_id: str
    # Map discrepancy index (as string) to decision
    decisions: dict[str, Literal["approve", "reject", "escalate"]]


class ResumeResponse(BaseModel):
    thread_id: str
    status: str
    approved: int
    rejected: int
    escalated: int
    message: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.post("/run", response_model=RunResponse)
def run_reconciliation() -> RunResponse:
    """
    Start a new reconciliation run.
    Fetches data, runs LLM comparison, pauses before human review.
    Returns the thread_id and list of discrepancies for the human to review.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    _graph.invoke(EMPTY_STATE, config)

    snapshot = _graph.get_state(config)
    discrepancies: list[Discrepancy] = snapshot.values.get("discrepancies", [])
    status = snapshot.values.get("status", "unknown")

    return RunResponse(
        thread_id=thread_id,
        status=status,
        discrepancy_count=len(discrepancies),
        discrepancies=discrepancies,
        message=(
            f"Found {len(discrepancies)} discrepancy(ies). "
            "POST to /resume with your decisions to complete."
            if discrepancies
            else "All transactions reconciled cleanly. No human review needed."
        ),
    )


@app.post("/resume", response_model=ResumeResponse)
def resume_reconciliation(body: ResumeRequest) -> ResumeResponse:
    """
    Resume a paused run after human review.
    Supply decisions (approve / reject / escalate) for each discrepancy index.
    """
    config = {"configurable": {"thread_id": body.thread_id}}

    snapshot = _graph.get_state(config)
    if not snapshot.values:
        raise HTTPException(status_code=404, detail=f"Thread '{body.thread_id}' not found.")
    if not snapshot.next:
        raise HTTPException(status_code=409, detail="This run has already completed.")

    # Convert string keys to int so human_review_node can look them up either way
    decisions = {int(k): v for k, v in body.decisions.items()}
    _graph.update_state(config, {"human_decisions": decisions})
    final = _graph.invoke(None, config)

    d = final.get("human_decisions", {})
    approved  = sum(1 for v in d.values() if v == "approve")
    rejected  = sum(1 for v in d.values() if v == "reject")
    escalated = sum(1 for v in d.values() if v == "escalate")

    return ResumeResponse(
        thread_id=body.thread_id,
        status=final.get("status", "unknown"),
        approved=approved,
        rejected=rejected,
        escalated=escalated,
        message=f"Run complete. {approved} approved, {rejected} rejected, {escalated} escalated.",
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
