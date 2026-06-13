"""
CsvLoader — reads bank_export.csv and stripe_export.csv into Pydantic models.

Expected CSV columns
--------------------
bank_export.csv   : id, date, amount, description, currency
stripe_export.csv : id, date, amount, description, currency, fee

All columns are required. currency defaults to "USD" if omitted. fee defaults to 0.0.
Dates must be ISO format: YYYY-MM-DD.
Amounts are floats. Negative values represent refunds / credits.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from agent.models import BankTransaction, StripeTransaction


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}. Expected YYYY-MM-DD.")


def _read_csv(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"CSV not found: {path}\n"
            "Run  python scripts/generate_test_data.py  to create sample files, "
            "or upload your own via the Streamlit UI."
        )
    for enc in ("utf-8", "latin-1", "cp1252", "utf-8-sig"):
        try:
            open(p, encoding=enc).read(1024)
            encoding = enc
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        encoding = "latin-1"

    with open(p, newline="", encoding=encoding) as f:
        return list(csv.DictReader(f))


class CsvLoader:
    def __init__(self, bank_path: str, stripe_path: str) -> None:
        self.bank_path   = bank_path
        self.stripe_path = stripe_path

    def fetch_bank(self) -> list[BankTransaction]:
        rows = _read_csv(self.bank_path)
        out = []
        for r in rows:
            out.append(BankTransaction(
                id          = r["id"].strip(),
                date        = _parse_date(r["date"]),
                amount      = float(r["amount"]),
                description = r["description"].strip(),
                currency    = r.get("currency", "USD").strip() or "USD",
            ))
        return out

    def fetch_stripe(self) -> list[StripeTransaction]:
        rows = _read_csv(self.stripe_path)
        out = []
        for r in rows:
            out.append(StripeTransaction(
                id          = r["id"].strip(),
                date        = _parse_date(r["date"]),
                amount      = float(r["amount"]),
                description = r["description"].strip(),
                currency    = r.get("currency", "USD").strip() or "USD",
                fee         = float(r.get("fee", 0.0) or 0.0),
            ))
        return out
