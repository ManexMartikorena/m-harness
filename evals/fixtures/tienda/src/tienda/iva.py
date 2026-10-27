"""El IVA de los precios."""

TIPO_GENERAL = 0.21


def calcular_iva(importe: float, tipo: float = TIPO_GENERAL) -> float:
    """El IVA de un importe, redondeado a céntimos."""
    return round(importe * tipo, 2)
