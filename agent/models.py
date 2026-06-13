from __future__ import annotations

from datetime import date
from typing import Literal, TypedDict

from pydantic import BaseModel


class BankTransaction(BaseModel):
    id: str
    date: date
    amount: float
    description: str
    currency: str = "USD"


class StripeTransaction(BaseModel):
    id: str
    date: date
    amount: float
    description: str
    currency: str = "USD"
    fee: float = 0.0


class Discrepancy(BaseModel):
    bank_txn_id: str        # "NONE" if transaction missing from bank side
    stripe_txn_id: str      # "NONE" if transaction missing from Stripe side
    reason: str
    confidence: Literal["low", "medium", "high"]
    suggested_action: str


class ReconciliationResult(BaseModel):
    """Structured output the LLM must return from reconcile_node."""
    discrepancies: list[Discrepancy]


class AgentState(TypedDict):
    bank_transactions: list[BankTransaction]
    stripe_transactions: list[StripeTransaction]
    discrepancies: list[Discrepancy]
    human_decisions: dict[int, str]   # discrepancy index -> "approve"/"reject"/"escalate"
    status: str
