"""Pedidos: líneas de cantidad y precio."""

from tienda.iva import calcular_iva


def total(lineas: list[tuple[int, float]]) -> float:
    """La suma de cantidad por precio de todas las líneas."""
    return round(sum(cantidad * precio for cantidad, precio in lineas), 2)


def total_con_iva(lineas: list[tuple[int, float]]) -> float:
    base = total(lineas)
    return round(base + calcular_iva(base), 2)
