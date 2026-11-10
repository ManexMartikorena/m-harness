import unittest
from datetime import date

from prestamos import dias_retraso, multa, multa_de_prestamo


class TestPrestamos(unittest.TestCase):
    def test_a_tiempo_no_hay_retraso(self) -> None:
        self.assertEqual(dias_retraso(date(2026, 3, 1), date(2026, 3, 2)), 0)

    def test_dias_de_retraso(self) -> None:
        self.assertEqual(dias_retraso(date(2026, 3, 5), date(2026, 3, 2)), 3)

    def test_multa_por_dia(self) -> None:
        self.assertEqual(multa(4), 2.0)

    def test_multa_de_un_prestamo(self) -> None:
        self.assertEqual(multa_de_prestamo(date(2026, 3, 5), date(2026, 3, 2)), 1.5)


if __name__ == "__main__":
    unittest.main()
