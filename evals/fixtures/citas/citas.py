"""Una agenda de citas mínima."""


def nueva(citas: list[str], texto: str) -> list[str]:
    """Las citas, con una más al final."""
    return [*citas, texto]


def primera(citas: list[str]) -> str | None:
    """La primera cita, o None si no hay ninguna."""
    return citas[0] if citas else None
