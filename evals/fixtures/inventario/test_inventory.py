import unittest

from inventory import Inventory


class TestInventory(unittest.TestCase):
    def test_add(self) -> None:
        stock = Inventory()
        stock.add("pen", 3, 1.5)
        stock.add("pen", 2, 9.9)
        self.assertEqual(stock.quantity("pen"), 5)
        self.assertEqual(stock.items["pen"].unit_price, 1.5)

    def test_remove(self) -> None:
        stock = Inventory()
        stock.add("pen", 3, 1.5)
        stock.remove("pen", 2)
        self.assertEqual(stock.quantity("pen"), 1)

    def test_remove_more_than_there_is_fails_and_keeps_the_stock(self) -> None:
        stock = Inventory()
        stock.add("pen", 3, 1.5)
        with self.assertRaises(ValueError):
            stock.remove("pen", 4)
        self.assertEqual(stock.quantity("pen"), 3)

    def test_remove_an_unknown_item_fails(self) -> None:
        with self.assertRaises(ValueError):
            Inventory().remove("ghost", 1)


if __name__ == "__main__":
    unittest.main()
