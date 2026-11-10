"""Préstamos de una biblioteca de barrio: retrasos y multas."""

from datetime import date

MULTA_POR_DIA = 0.5


def dias_retraso(entregado: date, limite: date) -> int:
    """Días que pasaron del límite; 0 si se entregó a tiempo."""
    return max(0, (entregado - limite).days)


def multa(dias: int) -> float:
    """Lo que se paga por `dias` de retraso, en euros."""
    return dias * MULTA_POR_DIA


def multa_de_prestamo(entregado: date, limite: date) -> float:
    """La multa de un préstamo entregado en `entregado`."""
    return multa(dias_retraso(entregado, limite))
