"""Tests de facturas."""

import unittest

from facturas.descuentos import descuento_cliente_001
from facturas.impuestos import iva, recargo_equivalencia, retencion_actividad_001
from facturas.tarifas import tarifa_zona_001


class FacturasTest(unittest.TestCase):
    def test_iva(self) -> None:
        self.assertEqual(iva(100, "general"), 21.0)
        self.assertEqual(iva(100, "reducido"), 10.0)

    def test_recargo_general(self) -> None:
        self.assertEqual(recargo_equivalencia(100, "general"), 5.2)

    def test_recargo_reducido(self) -> None:
        self.assertEqual(recargo_equivalencia(200, "reducido"), 2.8)

    def test_recargo_desconocido(self) -> None:
        with self.assertRaises(ValueError):
            recargo_equivalencia(100, "otro")

    def test_otras_funciones(self) -> None:
        self.assertGreater(tarifa_zona_001(2), 0)
        self.assertGreaterEqual(retencion_actividad_001(100), 0)
        self.assertGreaterEqual(descuento_cliente_001(5000), 0)


if __name__ == "__main__":
    unittest.main()
