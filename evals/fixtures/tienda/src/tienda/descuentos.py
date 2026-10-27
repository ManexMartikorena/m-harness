"""Descuentos sobre los precios."""


def aplicar_descuento(precio: float, porcentaje: float) -> float:
    """El precio con un descuento del porcentaje dado."""
    return round(precio * porcentaje / 100, 2)
