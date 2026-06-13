"""
BankOnlyLoader — reads a single bank CSV (including Kaggle format) and
derives the Stripe side automatically using derive_stripe().

Supported column layouts
------------------------
Standard (our own format):
    id, date, amount, description, currency

Kaggle fraud detection dataset (kartik2112/fraud-detection):
    trans_num, trans_date_trans_time, amt, merchant, category, ...

Generic fallback — tries to sniff which columns map to id/date/amount/description.
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from agent.models import BankTransaction, StripeTransaction
from agent.loaders.derive_stripe import derive_stripe


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d",
                "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


def _sniff_columns(headers: list[str]) -> dict[str, str]:
    """
    Returns a mapping of role → actual column name.
    Roles: id, date, amount, description
    """
    h = [c.lower().strip() for c in headers]

    def pick(*candidates) -> str | None:
        for c in candidates:
            if c in h:
                return headers[h.index(c)]
        return None

    return {
        "id":          pick("trans_num", "id", "transaction_id", "txn_id", "trans_id") or headers[0],
        "date":        pick("trans_date_trans_time", "date", "trans_date", "transaction_date", "datetime") or headers[1],
        "amount":      pick("amt", "amount", "transaction_amount", "debit", "credit") or headers[2],
        "description": pick("merchant", "description", "merchant_name", "name", "payee", "category") or headers[3],
        "currency":    pick("currency", "curr") or None,
    }


class BankOnlyLoader:
    """
    Load a single bank CSV and auto-derive the Stripe side.
    Works with our standard format, the Kaggle fraud CSV, or any
    generic transaction CSV — column names are sniffed automatically.
    """

    def __init__(self, bank_path: str, max_rows: int = 300, seed: int = 42) -> None:
        self.bank_path = bank_path
        self.max_rows  = max_rows
        self.seed      = seed
        self._bank: list[BankTransaction] | None = None

    def _load(self) -> list[BankTransaction]:
        if self._bank is not None:
            return self._bank

        p = Path(self.bank_path)
        if not p.exists():
            raise FileNotFoundError(f"Bank CSV not found: {self.bank_path}")

        for enc in ("utf-8", "latin-1", "cp1252", "utf-8-sig"):
            try:
                open(p, encoding=enc).read(1024)
                encoding = enc
                break
            except (UnicodeDecodeError, LookupError):
                continue
        else:
            encoding = "latin-1"
        print(f"  [csv] detected encoding: {encoding}")

        with open(p, newline="", encoding=encoding) as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames or []
            col = _sniff_columns(list(headers))

            rows = []
            for i, row in enumerate(reader):
                if i >= self.max_rows:
                    break
                try:
                    amount = float(row[col["amount"]])
                    txn_date = _parse_date(row[col["date"]])
                except (ValueError, KeyError):
                    continue

                rows.append(BankTransaction(
                    id          = str(row[col["id"]]).strip() or f"B{i+1:04d}",
                    date        = txn_date,
                    amount      = round(amount, 2),
                    description = str(row[col["description"]]).strip(),
                    currency    = (str(row[col["currency"]]).strip() if col["currency"] and col["currency"] in row else "USD") or "USD",
                ))

        self._bank = rows
        return rows

    def fetch_bank(self) -> list[BankTransaction]:
        return self._load()

    def fetch_stripe(self) -> list[StripeTransaction]:
        return derive_stripe(self._load(), seed=self.seed)
