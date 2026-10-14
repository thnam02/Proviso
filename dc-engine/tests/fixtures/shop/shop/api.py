"""Entry points used by the web layer."""

from decimal import Decimal

import shop.tax as t
from shop import charge
from shop.models import User


def checkout(user: User, amount: Decimal):
    """Charge the user for their cart."""
    return charge(user, amount)


def preview(amount: Decimal, region: str) -> Decimal:
    return amount + t.compute(amount, region)


class Service:
    def run(self) -> int:
        return self.helper() + 1

    def helper(self) -> int:
        return 41
