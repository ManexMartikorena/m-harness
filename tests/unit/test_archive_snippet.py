"""The fragment of an archived item that a search shows (spec hito 11,
§1.9): maha's own, with a bounded cost, instead of FTS5's snippet()."""

from mharness.domain.archive import SNIPPET_CHARS, snippet


def test_a_short_text_comes_whole() -> None:
    text = "013458 ERROR payment failed code=PX-4471"

    assert snippet(text, ["error"]) == text


def test_the_window_has_the_most_words_of_the_query() -> None:
    text = "iva " + "relleno " * 200 + "el iva reducido es del 4 % " + "relleno " * 200

    found = snippet(text, ["iva", "reducido"])

    assert "el iva reducido es del 4 %" in found
    assert found.startswith("…")
    assert found.endswith("…")
    assert len(found) <= SNIPPET_CHARS + 2


def test_it_finds_words_without_their_accents_or_case() -> None:
    text = "x " * 300 + "La Función calcula el IVA " + "y " * 300

    assert "La Función calcula el IVA" in snippet(text, ["funcion", "iva"])


def test_it_matches_whole_words() -> None:
    text = "linea 12345\n" * 50 + "linea 1234\n" + "linea 12345\n" * 50

    found = snippet(text, ["linea", "1234"])

    assert "linea 1234\n" in found + "\n"


def test_without_any_of_the_words_it_gives_the_start() -> None:
    text = "uno dos tres " * 100

    found = snippet(text, ["cuatro"])

    assert found.startswith("uno dos tres")
    assert found.endswith("…")


def test_the_cost_is_bounded_with_words_everywhere() -> None:
    # 400,000 lines, as the output that hung FTS5's snippet(): the scan
    # stops after a fixed number of places.
    text = "".join(f"linea numero {n}\n" for n in range(1, 400_001))

    found = snippet(text, ["linea", "numero", "123456"])

    assert "linea numero 123456" in found
