"""
derive_stripe — takes a list of BankTransaction objects and produces a
realistic StripeTransaction list by injecting known discrepancy types.

Used when the user uploads only a bank CSV and has no Stripe export.
The agent treats the bank as the source of truth and the derived Stripe
side as "what the payment processor recorded" — with deliberate noise.
"""
from __future__ import annotations

import random
from datetime import timedelta

from agent.models import BankTransaction, StripeTransaction

MERCHANT_VARIANTS: dict[str, list[str]] = {
    "amazon":       ["AMZN MKTP US", "Amazon.com", "AMAZON MARKETPLACE", "Amzn Digital"],
    "starbucks":    ["STARBUCKS STORE #4021", "Starbucks", "STARBUCKS #1042", "Starbucks Coffee"],
    "uber":         ["Uber *trip", "UBER", "UBER* TRIP", "Uber Technologies"],
    "netflix":      ["NETFLIX.COM", "Netflix", "NETFLIX INC"],
    "spotify":      ["Spotify Premium", "SPOTIFY", "Spotify AB"],
    "apple":        ["APPLE.COM/BILL", "Apple", "Apple Store", "iTunes"],
    "google":       ["Google *Services", "GOOGLE", "Google Play", "GOOGLE LLC"],
    "adobe":        ["Adobe Creative Cloud", "ADOBE SYSTEMS", "ADOBE *CREATIVE"],
    "microsoft":    ["Microsoft 365", "MICROSOFT", "MSFT"],
    "walmart":      ["WALMART SUPERCENTER", "Walmart", "WAL-MART"],
    "target":       ["TARGET", "Target Store", "TARGET 00"],
    "costco":       ["COSTCO WHSE", "Costco", "Costco Wholesale"],
    "lyft":         ["Lyft", "LYFT *RIDE", "Lyft Inc"],
    "delta":        ["DELTA AIR", "Delta Airlines", "DELTA AIR LINES"],
    "united":       ["UNITED AIRLINES", "United", "UA*TICKET"],
}

EXTRA_STRIPE: list[tuple[str, float]] = [
    ("Dropbox", 11.99), ("Zoom", 14.99), ("Slack", 7.25),
    ("Notion", 8.00), ("GitHub", 4.00), ("Figma", 12.00),
]


def _merchant_variant(description: str) -> str | None:
    key = description.lower().strip()
    for canonical, variants in MERCHANT_VARIANTS.items():
        if canonical in key or any(v.lower() in key for v in variants):
            others = [v for v in variants if v.lower() not in key]
            return random.choice(others) if others else None
    return None


def derive_stripe(
    bank: list[BankTransaction],
    seed: int = 42,
    rate_missing:   float = 0.03,
    rate_rounding:  float = 0.05,
    rate_date_drift: float = 0.04,
    rate_merchant:  float = 0.05,
    rate_duplicate: float = 0.02,
    rate_extra:     float = 0.02,
) -> list[StripeTransaction]:
    """
    Derive a Stripe transaction list from bank transactions with injected noise.

    Rates are fractions of total rows (0.05 = 5%).
    """
    random.seed(seed)
    stripe: list[StripeTransaction] = []

    for txn in bank:
        # 3% missing from Stripe entirely
        if random.random() < rate_missing:
            continue

        amount = txn.amount
        txn_date = txn.date
        description = txn.description

        r = random.random()

        if r < rate_rounding:
            # off-by-cent rounding
            delta = random.choice([-0.03, -0.02, -0.01, 0.01, 0.02, 0.03])
            amount = round(amount + delta, 2)

        elif r < rate_rounding + rate_date_drift:
            # date shifted ±1 day
            txn_date = txn_date + timedelta(days=random.choice([-1, 1]))

        elif r < rate_rounding + rate_date_drift + rate_merchant:
            # merchant name variant
            variant = _merchant_variant(description)
            if variant:
                description = variant

        fee = round(abs(amount) * 0.029 + 0.30, 2) if amount > 0 else 0.0

        stripe.append(StripeTransaction(
            id          = "S" + txn.id[1:] if txn.id.startswith("B") else "S_" + txn.id,
            date        = txn_date,
            amount      = amount,
            description = description,
            currency    = txn.currency,
            fee         = fee,
        ))

        # 2% duplicate
        if random.random() < rate_duplicate:
            dup = stripe[-1]
            stripe.append(StripeTransaction(
                id          = dup.id + "_DUP",
                date        = dup.date,
                amount      = dup.amount,
                description = dup.description,
                currency    = dup.currency,
                fee         = dup.fee,
            ))

    # extra charges on Stripe only
    n_extra = max(1, int(len(bank) * rate_extra))
    for i in range(n_extra):
        merchant, amount = random.choice(EXTRA_STRIPE)
        ref = bank[random.randint(0, len(bank) - 1)]
        stripe.append(StripeTransaction(
            id          = f"SEXT{i+1:03d}",
            date        = ref.date,
            amount      = amount,
            description = merchant,
            currency    = "USD",
            fee         = round(amount * 0.029 + 0.30, 2),
        ))

    return stripe
