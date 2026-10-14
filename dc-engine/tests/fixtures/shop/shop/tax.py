"""Tax rates by region."""

from decimal import Decimal

RATES = {"AU": Decimal("0.10"), "VN": Decimal("0.08")}


def compute(amount: Decimal, region: str) -> Decimal:
    """Tax owed on an amount in a region."""
    return amount * RATES.get(region, Decimal("0"))
