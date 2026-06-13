from langchain_core.tools import tool

MERCHANT_ALIASES: dict[str, str] = {
    "amzn mktp us": "Amazon",
    "amazon.com": "Amazon",
    "amazon": "Amazon",
    "starbucks store": "Starbucks",
    "sbux": "Starbucks",
    "starbucks": "Starbucks",
    "uber *trip": "Uber",
    "uber": "Uber",
    "wholefds": "Whole Foods",
    "whole foods": "Whole Foods",
    "wf": "Whole Foods",
}


@tool
def lookup_merchant_alias(name: str) -> str:
    """Look up the canonical merchant name for a given description or alias.
    Use this when two transaction descriptions might refer to the same vendor.
    Returns the canonical name if known, or 'UNKNOWN' if not in the alias table.
    """
    return MERCHANT_ALIASES.get(name.lower().strip(), "UNKNOWN")
