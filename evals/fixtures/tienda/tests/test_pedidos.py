import unittest

from tienda import informe, pedidos


class TestPedidos(unittest.TestCase):
    def test_total(self) -> None:
        self.assertEqual(pedidos.total([(2, 10.0), (1, 5.5)]), 25.5)

    def test_total_con_iva(self) -> None:
        self.assertEqual(pedidos.total_con_iva([(1, 100.0)]), 121.0)

    def test_resumen(self) -> None:
        self.assertEqual(informe.resumen([(1, 3.0)]), "1 líneas, 3.00 EUR")


if __name__ == "__main__":
    unittest.main()
