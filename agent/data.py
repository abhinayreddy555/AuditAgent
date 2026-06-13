from datetime import date
from agent.models import BankTransaction, StripeTransaction


def fetch_bank_data() -> list[BankTransaction]:
    """Simulates pulling records from a bank ledger API."""
    return [
        # 1. Clean match (baseline)
        BankTransaction(id="B001", date=date(2024, 6, 1), amount=500.00, description="Payroll deposit"),
        # 2. Off-by-cent rounding — bank $120.00, Stripe $120.02
        BankTransaction(id="B002", date=date(2024, 6, 2), amount=120.00, description="AMZN MKTP US"),
        # 3. Missing from Stripe entirely
        BankTransaction(id="B003", date=date(2024, 6, 3), amount=29.99, description="Netflix subscription"),
        # 4. Duplicate on bank side — same charge posted twice
        BankTransaction(id="B004", date=date(2024, 6, 4), amount=85.00, description="Gym membership"),
        BankTransaction(id="B005", date=date(2024, 6, 4), amount=85.00, description="Gym membership"),
        # 5. Refund pair — should net to zero, not flagged
        BankTransaction(id="B006", date=date(2024, 6, 5), amount=200.00, description="Airline ticket"),
        BankTransaction(id="B007", date=date(2024, 6, 6), amount=-200.00, description="Airline ticket refund"),
        # 6. Date shifted by 1 day (timezone)
        BankTransaction(id="B008", date=date(2024, 6, 7), amount=45.00, description="Uber ride"),
        # 7. Same vendor, different merchant name
        BankTransaction(id="B009", date=date(2024, 6, 9), amount=12.50, description="STARBUCKS STORE #4021"),
        # 8. STRESS TEST — genuinely ambiguous: same amount + day, slightly different description
        #    Could be two separate purchases or one transaction with inconsistent labelling
        BankTransaction(id="B010", date=date(2024, 6, 11), amount=54.99, description="ADOBE SYSTEMS"),
    ]


def fetch_stripe_data() -> list[StripeTransaction]:
    """Simulates pulling records from the Stripe API."""
    return [
        # 1. Clean match
        StripeTransaction(id="S001", date=date(2024, 6, 1), amount=500.00, description="Payroll deposit", fee=0.00),
        # 2. Off-by-cent
        StripeTransaction(id="S002", date=date(2024, 6, 2), amount=120.02, description="Amazon.com", fee=0.35),
        # 3. Netflix absent — intentionally omitted
        # 4. Only ONE gym charge on Stripe
        StripeTransaction(id="S003", date=date(2024, 6, 4), amount=85.00, description="Gym membership", fee=0.25),
        # 5. Refund pair — present on both sides, should net cleanly
        StripeTransaction(id="S004", date=date(2024, 6, 5), amount=200.00, description="Airline ticket", fee=0.50),
        StripeTransaction(id="S005", date=date(2024, 6, 6), amount=-200.00, description="Airline ticket refund", fee=0.00),
        # 6. Date shifted +1 day
        StripeTransaction(id="S006", date=date(2024, 6, 8), amount=45.00, description="Uber *trip", fee=0.13),
        # 7. Same vendor as B009 but different name
        StripeTransaction(id="S007", date=date(2024, 6, 9), amount=12.50, description="Starbucks", fee=0.04),
        # Missing from bank
        StripeTransaction(id="S008", date=date(2024, 6, 10), amount=9.99, description="Spotify Premium", fee=0.03),
        # 8. STRESS TEST — same amount + date as B010, but "Adobe Creative Cloud" vs "ADOBE SYSTEMS"
        #    Intentionally ambiguous: probably the same charge, but cannot be certain
        StripeTransaction(id="S009", date=date(2024, 6, 11), amount=54.99, description="Adobe Creative Cloud", fee=0.16),
    ]
