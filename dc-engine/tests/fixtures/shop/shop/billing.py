"""Billing helpers."""

from decimal import Decimal

from . import tax
from .models import User


class Receipt:
    """A payment receipt."""

    def __init__(self, user: User, amount: Decimal) -> None:
        self.user = user
        self.amount = amount

    @property
    def total(self) -> Decimal:
        """Amount including tax."""
        return self.amount + tax.compute(self.amount, self.user.region)


def validate_amount(amount: Decimal) -> None:
    """Reject negative amounts."""
    if amount < 0:
        raise ValueError("negative amount")


def charge(user: User, amount: Decimal) -> Receipt:
    """Charge a user and return a receipt."""
    validate_amount(amount)
    receipt = Receipt(user, amount)
    user.notify(f"charged {receipt.total}")
    return receipt
