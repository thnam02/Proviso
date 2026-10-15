"""Domain models."""


class User:
    """A customer."""

    def __init__(self, name: str, region: str) -> None:
        self.name = name
        self.region = region
        self.inbox: list[str] = []

    def notify(self, message: str) -> None:
        """Send the user a message."""
        self.inbox.append(message)


class Admin(User):
    """A staff member; notifications are also logged."""

    def notify(self, message: str) -> None:
        super().notify(message)
        self.log(message)

    def log(self, message: str) -> None:
        print(f"[admin {self.name}] {message}")

    @property
    def label(self) -> str:
        return self.name

    @label.setter
    def label(self, value: str) -> None:
        self.name = value
