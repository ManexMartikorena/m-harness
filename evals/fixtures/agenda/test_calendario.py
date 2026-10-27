import unittest

from calendario import dia_del_anio, dias_del_mes, es_bisiesto


class TestCalendario(unittest.TestCase):
    def test_bisiestos(self) -> None:
        self.assertTrue(es_bisiesto(2024))
        self.assertFalse(es_bisiesto(2023))
        self.assertTrue(es_bisiesto(2000))
        self.assertFalse(es_bisiesto(1900))
        self.assertFalse(es_bisiesto(2100))

    def test_febrero(self) -> None:
        self.assertEqual(dias_del_mes(1900, 2), 28)
        self.assertEqual(dias_del_mes(2000, 2), 29)

    def test_dia_del_anio(self) -> None:
        self.assertEqual(dia_del_anio(2024, 3, 1), 61)
        self.assertEqual(dia_del_anio(2100, 3, 1), 60)


if __name__ == "__main__":
    unittest.main()
