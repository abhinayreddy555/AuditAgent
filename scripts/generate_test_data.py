"""
Generate realistic bank_export.csv and stripe_export.csv for testing.

Usage
-----
# Generate 200-row sample (default):
    python scripts/generate_test_data.py

# Generate larger set:
    python scripts/generate_test_data.py --rows 500

# Use a real public dataset (Kaggle fraud detection CSV):
#   Download: https://www.kaggle.com/datasets/kartik2112/fraud-detection
#   Place fraudTrain.csv next to this script, then:
    python scripts/generate_test_data.py --kaggle scripts/fraudTrain.csv --rows 300

Output
------
    data/bank_export.csv
    data/stripe_export.csv

Discrepancy types injected into the Stripe side
------------------------------------------------
  rounding    5% of rows get ± $0.01–$0.03 added to amount
  missing     3% of rows are dropped (transaction absent from Stripe)
  date_drift  4% of rows get date shifted by ±1 day
  duplicate   2% of rows are duplicated (double-posted on Stripe)
  merchant    5% of rows get a merchant name variant applied
  extra       2% of rows exist only on Stripe (not in bank)

The bank CSV is the authoritative source.  The Stripe CSV is derived from it
with the above noise, so Claude has never seen these transactions before.
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

# ── Merchant name variants ─────────────────────────────────────────────────────

MERCHANT_VARIANTS: dict[str, list[str]] = {
    "Amazon":        ["AMZN MKTP US", "Amazon.com", "AMAZON MARKETPLACE", "Amzn Digital"],
    "Starbucks":     ["STARBUCKS STORE #4021", "Starbucks", "STARBUCKS #1042", "Starbucks Coffee"],
    "Uber":          ["Uber *trip", "UBER", "UBER* TRIP", "Uber Technologies"],
    "Netflix":       ["NETFLIX.COM", "Netflix", "Netflix Subscription", "NETFLIX INC"],
    "Spotify":       ["Spotify Premium", "SPOTIFY", "Spotify AB", "SPOTIFY USA"],
    "Apple":         ["APPLE.COM/BILL", "Apple", "Apple Store", "iTunes"],
    "Google":        ["Google *Services", "GOOGLE", "Google Play", "GOOGLE LLC"],
    "Adobe":         ["Adobe Creative Cloud", "ADOBE SYSTEMS", "Adobe Inc", "ADOBE *CREATIVE"],
    "Microsoft":     ["Microsoft 365", "MICROSOFT", "MSFT", "Microsoft Corp"],
    "Walmart":       ["WALMART SUPERCENTER", "Walmart", "WAL-MART", "Walmart.com"],
    "Target":        ["TARGET", "Target Store", "TARGET 00", "target.com"],
    "Costco":        ["COSTCO WHSE", "Costco", "COSTCO GAS", "Costco Wholesale"],
    "Whole Foods":   ["WHOLEFDS", "Whole Foods Market", "WHOLE FOODS", "WFM"],
    "Trader Joes":   ["TRADER JOE S", "Trader Joe's", "TRADER JOES", "TJs"],
    "Gym":           ["Planet Fitness", "PLANET FITNESS", "24 HOUR FITNESS", "Anytime Fitness"],
    "AT&T":          ["AT&T", "ATT*BILL", "AT&T Services", "AT AND T"],
    "Verizon":       ["Verizon Wireless", "VZWRLSS", "VERIZON", "Verizon"],
    "Delta":         ["DELTA AIR", "Delta Airlines", "DELTA AIR LINES", "Delta"],
    "United":        ["UNITED AIRLINES", "United", "UA*TICKET", "United Air"],
    "Lyft":          ["Lyft", "LYFT *RIDE", "Lyft Inc", "LYFT"],
}

CANONICAL_TO_VARIANTS: dict[str, list[str]] = MERCHANT_VARIANTS

ALL_MERCHANTS: list[tuple[str, float]] = [
    ("Amazon", 89.99), ("Starbucks", 6.75), ("Uber", 22.50),
    ("Netflix", 15.99), ("Spotify", 9.99), ("Apple", 4.99),
    ("Google", 1.99), ("Adobe", 54.99), ("Microsoft", 12.99),
    ("Walmart", 134.50), ("Target", 67.20), ("Costco", 212.40),
    ("Whole Foods", 78.30), ("Trader Joes", 43.10), ("Gym", 45.00),
    ("AT&T", 89.00), ("Verizon", 105.00), ("Delta", 320.00),
    ("United", 289.00), ("Lyft", 18.75),
]

EXTRA_STRIPE_MERCHANTS = [
    ("Dropbox", 11.99), ("Zoom", 14.99), ("Slack", 7.25),
    ("Notion", 8.00), ("GitHub", 4.00),
]


# ── Synthetic data generation ──────────────────────────────────────────────────

def _generate_synthetic(n: int, seed: int = 42) -> list[dict]:
    random.seed(seed)
    start = date(2024, 1, 1)
    rows = []
    for i in range(n):
        merchant, base_amount = random.choice(ALL_MERCHANTS)
        amount = round(base_amount * random.uniform(0.85, 1.15), 2)
        txn_date = start + timedelta(days=random.randint(0, 364))
        rows.append({
            "id":          f"B{i+1:04d}",
            "date":        txn_date.isoformat(),
            "amount":      amount,
            "description": random.choice(CANONICAL_TO_VARIANTS.get(merchant, [merchant])),
            "currency":    "USD",
            "canonical":   merchant,
        })
    return rows


def _load_kaggle(path: str, n: int) -> list[dict]:
    """
    Adapts the Kaggle fraud detection CSV to our format.
    Expected columns: trans_num, trans_date_trans_time, amt, merchant, ...
    """
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= n:
                break
            try:
                txn_date = row.get("trans_date_trans_time", "")[:10]
                date.fromisoformat(txn_date)
            except ValueError:
                continue
            merchant = row.get("merchant", "Unknown").replace("fraud_", "").strip()
            rows.append({
                "id":          f"B{i+1:04d}",
                "date":        txn_date,
                "amount":      round(float(row.get("amt", 0)), 2),
                "description": merchant,
                "currency":    "USD",
                "canonical":   merchant,
            })
    return rows


# ── Noise injection ────────────────────────────────────────────────────────────

def _inject_discrepancies(bank_rows: list[dict], seed: int = 42) -> list[dict]:
    random.seed(seed + 1)
    stripe_rows = []
    extra_ids = set()

    for row in bank_rows:
        r = float(random.random())

        # 3% missing from Stripe
        if r < 0.03:
            continue

        s = row.copy()
        s["id"]  = "S" + row["id"][1:]
        s["fee"] = round(float(row["amount"]) * 0.029 + 0.30, 2)

        rng = float(random.random())

        # 5% rounding error
        if rng < 0.05:
            s["amount"] = round(float(row["amount"]) + random.choice([-0.03, -0.02, -0.01, 0.01, 0.02, 0.03]), 2)

        # 4% date drift
        elif rng < 0.09:
            d = date.fromisoformat(row["date"])
            s["date"] = (d + timedelta(days=random.choice([-1, 1]))).isoformat()

        # 5% merchant name variant
        elif rng < 0.14:
            canonical = row.get("canonical", "")
            variants  = CANONICAL_TO_VARIANTS.get(canonical, [])
            if variants:
                current = row["description"]
                others  = [v for v in variants if v != current]
                if others:
                    s["description"] = random.choice(others)

        stripe_rows.append(s)

        # 2% duplicate — same transaction posted twice
        if random.random() < 0.02:
            dup = s.copy()
            dup["id"] = s["id"] + "_DUP"
            stripe_rows.append(dup)

    # 2% extra on Stripe only (charge bank never saw)
    n_extra = max(1, int(len(bank_rows) * 0.02))
    for i in range(n_extra):
        merchant, amount = random.choice(EXTRA_STRIPE_MERCHANTS)
        d = date.fromisoformat(bank_rows[random.randint(0, len(bank_rows)-1)]["date"])
        stripe_rows.append({
            "id":          f"SEXT{i+1:03d}",
            "date":        d.isoformat(),
            "amount":      amount,
            "description": merchant,
            "currency":    "USD",
            "fee":         round(amount * 0.029 + 0.30, 2),
        })

    return stripe_rows


# ── Write CSVs ─────────────────────────────────────────────────────────────────

BANK_FIELDS   = ["id", "date", "amount", "description", "currency"]
STRIPE_FIELDS = ["id", "date", "amount", "description", "currency", "fee"]


def _write_csv(path: str, rows: list[dict], fields: list[str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate reconciliation test data")
    parser.add_argument("--rows",   type=int, default=200, help="Number of bank transactions")
    parser.add_argument("--kaggle", type=str, default=None, help="Path to Kaggle fraudTrain.csv")
    parser.add_argument("--out",    type=str, default="data", help="Output directory")
    parser.add_argument("--sample", action="store_true", help="Write to data/sample/ instead")
    args = parser.parse_args()

    out_dir = "data/sample" if args.sample else args.out

    print(f"Generating {args.rows} bank transactions...")
    if args.kaggle:
        print(f"  Source: Kaggle dataset at {args.kaggle}")
        bank_rows = _load_kaggle(args.kaggle, args.rows)
    else:
        print("  Source: synthetic (no Kaggle file provided)")
        bank_rows = _generate_synthetic(args.rows)

    print("Injecting discrepancies into Stripe side...")
    stripe_rows = _inject_discrepancies(bank_rows)

    bank_path   = os.path.join(out_dir, "bank_export.csv")
    stripe_path = os.path.join(out_dir, "stripe_export.csv")

    _write_csv(bank_path,   bank_rows,   BANK_FIELDS)
    _write_csv(stripe_path, stripe_rows, STRIPE_FIELDS)

    n_missing   = len(bank_rows) - sum(1 for r in stripe_rows if not r["id"].startswith("SEXT"))
    n_extra     = sum(1 for r in stripe_rows if r["id"].startswith("SEXT"))
    n_dup       = sum(1 for r in stripe_rows if r["id"].endswith("_DUP"))

    print(f"\nDone.")
    print(f"  {bank_path}   — {len(bank_rows)} rows")
    print(f"  {stripe_path} — {len(stripe_rows)} rows")
    print(f"\nDiscrepancy summary:")
    print(f"  Missing from Stripe : ~{n_missing} txns")
    print(f"  Extra on Stripe only: {n_extra} txns")
    print(f"  Duplicates          : {n_dup} txns")
    print(f"  + rounding / date drift / merchant variants injected at ~5% each")
    print(f"\nSet in .env:")
    print(f"  DATA_SOURCE=csv")
    print(f"  BANK_CSV_PATH={bank_path}")
    print(f"  STRIPE_CSV_PATH={stripe_path}")


if __name__ == "__main__":
    main()
