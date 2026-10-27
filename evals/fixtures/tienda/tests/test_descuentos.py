import unittest

from tienda.descuentos import aplicar_descuento


class TestDescuentos(unittest.TestCase):
    def test_un_veinte_por_ciento(self) -> None:
        self.assertEqual(aplicar_descuento(100, 20), 80)

    def test_sin_descuento(self) -> None:
        self.assertEqual(aplicar_descuento(59.9, 0), 59.9)


if __name__ == "__main__":
    unittest.main()
