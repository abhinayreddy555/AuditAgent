"""
FixtureLoader — wraps the original hardcoded demo data.
Used when DATA_SOURCE=fixture (the default).
"""
from agent.models import BankTransaction, StripeTransaction
from agent.data import fetch_bank_data, fetch_stripe_data


class FixtureLoader:
    def fetch_bank(self) -> list[BankTransaction]:
        return fetch_bank_data()

    def fetch_stripe(self) -> list[StripeTransaction]:
        return fetch_stripe_data()
