"""A small stock inventory."""

from dataclasses import dataclass, field


@dataclass
class Item:
    name: str
    quantity: int
    unit_price: float


@dataclass
class Inventory:
    items: dict[str, Item] = field(default_factory=dict)

    def add(self, name: str, quantity: int, unit_price: float) -> None:
        """Add stock; a known item keeps its price."""
        if name in self.items:
            self.items[name].quantity += quantity
        else:
            self.items[name] = Item(name, quantity, unit_price)

    def remove(self, name: str, quantity: int) -> None:
        """Take stock out."""
        self.items[name].quantity -= quantity

    def quantity(self, name: str) -> int:
        item = self.items.get(name)
        return item.quantity if item else 0
