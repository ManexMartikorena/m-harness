"""Un informe de texto de un pedido."""

from tienda import pedidos


def resumen(lineas: list[tuple[int, float]]) -> str:
    return f"{len(lineas)} líneas, {pedidos.total(lineas):.2f} EUR"
