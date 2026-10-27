import unittest

from texto import slugify


class TestSlugify(unittest.TestCase):
    def test_palabras(self) -> None:
        self.assertEqual(slugify("Hola Mundo"), "hola-mundo")

    def test_tildes_y_signos(self) -> None:
        self.assertEqual(slugify("¡Año nuevo, vida nueva!"), "ano-nuevo-vida-nueva")

    def test_espacios_de_sobra(self) -> None:
        self.assertEqual(slugify("  ya   está  "), "ya-esta")

    def test_numeros(self) -> None:
        self.assertEqual(slugify("Versión 2.0"), "version-2-0")

    def test_vacio(self) -> None:
        self.assertEqual(slugify(""), "")


if __name__ == "__main__":
    unittest.main()
