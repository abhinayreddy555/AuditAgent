"""
DataLoader protocol — every source (fixture, CSV, API) implements this.
fetch_data_node in graph.py calls get_loader() and never touches the source directly.
"""
from __future__ import annotations

import os
from typing import Protocol

from agent.models import BankTransaction, StripeTransaction


class DataLoader(Protocol):
    def fetch_bank(self) -> list[BankTransaction]: ...
    def fetch_stripe(self) -> list[StripeTransaction]: ...


def get_loader() -> DataLoader:
    """
    Reads DATA_SOURCE from the environment and returns the right loader.

    DATA_SOURCE=fixture    →  built-in hardcoded demo data (default)
    DATA_SOURCE=csv        →  reads BANK_CSV_PATH and STRIPE_CSV_PATH
    DATA_SOURCE=bank_only  →  reads BANK_CSV_PATH, derives Stripe side automatically
    """
    source = os.environ.get("DATA_SOURCE", "fixture").lower()

    if source == "csv":
        from agent.loaders.csv_loader import CsvLoader
        bank_path   = os.environ.get("BANK_CSV_PATH",   "data/bank_export.csv")
        stripe_path = os.environ.get("STRIPE_CSV_PATH", "data/stripe_export.csv")
        return CsvLoader(bank_path, stripe_path)

    if source == "bank_only":
        from agent.loaders.bank_only_loader import BankOnlyLoader
        bank_path = os.environ.get("BANK_CSV_PATH", "data/bank_export.csv")
        max_rows  = int(os.environ.get("BANK_MAX_ROWS", 200))
        return BankOnlyLoader(bank_path, max_rows=max_rows)

    from agent.loaders.fixture import FixtureLoader
    return FixtureLoader()
